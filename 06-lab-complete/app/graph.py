from __future__ import annotations

from pathlib import Path
from typing import Any

from app.config import Settings
from app.state import ShoppingState


import json
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph import StateGraph, END
from functools import partial

from app.config import Settings
from app.state import ShoppingState
from app.data_access import ShoppingDataStore
from rag.vector_store import ChromaPolicyStore
from app.utils import timestamp_utc


class ShoppingAssistant:
    """Multi-Agent coordinator for Shopping Assistant lab using LangGraph."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings.load()

        # Load chat model from provider
        from provider import get_chat_model
        self.model = get_chat_model(self.settings)
        
        # Load dataset order/customer
        from app.data_access import ShoppingDataStore, build_data_tools
        self.store = ShoppingDataStore(self.settings.orders_path)
        
        # Load vector store for policy
        from rag.embeddings import SentenceTransformerEmbeddings
        from rag.vector_store import ChromaPolicyStore
        self.embedding_model = SentenceTransformerEmbeddings(self.settings.embedding_model_name)
        self.policy_store = ChromaPolicyStore(
            persist_directory=self.settings.chroma_dir,
            embedding_model=self.embedding_model
        )
        
        # Build worker tools
        self.tools = build_data_tools(self.store)
        
        # Compile LangGraph
        self.graph = build_graph(
            model=self.model,
            store=self.store,
            policy_store=self.policy_store,
            tools=self.tools
        )

    def ask(
        self,
        question: str,
        trace_file: Path | None = None,
        rebuild_index: bool = False,
    ) -> dict[str, Any]:
        if rebuild_index:
            self.policy_store.rebuild(self.settings.policy_path)
        else:
            self.policy_store.ensure_index(self.settings.policy_path)
            
        initial_state = {
            "question": question,
            "trace": []
        }
        
        result = self.graph.invoke(initial_state)
        
        trace_data = result.get("trace", [])
        if trace_file:
            trace_file.parent.mkdir(parents=True, exist_ok=True)
            with open(trace_file, "w", encoding="utf-8") as f:
                json.dump(trace_data, f, ensure_ascii=False, indent=2)
                
        payload = {
            "route": result.get("route", {}),
            "policy_result": result.get("policy_result", {}),
            "data_result": result.get("data_result", {}),
            "final_answer": result.get("final_answer", ""),
            "trace": trace_data
        }
        return payload

    def run_batch(
        self,
        test_file: Path,
        output_dir: Path,
        rebuild_index: bool = False,
    ) -> dict[str, Any]:
        if not test_file.exists():
            raise FileNotFoundError(f"Test file not found at {test_file}")
            
        with open(test_file, "r", encoding="utf-8") as f:
            test_cases = json.load(f)
            
        output_dir.mkdir(parents=True, exist_ok=True)
        
        results = []
        correct_routes = 0
        correct_status = 0
        
        for case in test_cases:
            case_id = case.get("id")
            question = case.get("question")
            expected_route = case.get("expected_route", [])
            expected_status = case.get("expected_status", "ok")
            
            trace_filename = f"trace_{case_id}.json"
            trace_path = output_dir / trace_filename
            
            # Run the assistant
            res = self.ask(question, trace_file=trace_path, rebuild_index=rebuild_index)
            # Rebuild index only once
            rebuild_index = False
            
            # Derive actual status: route status OR data_result not_found
            route_info = res.get("route", {})
            actual_status = route_info.get("status", "ok")
            
            # If route said ok but data worker found nothing, bubble up not_found
            if actual_status == "ok":
                data_res = res.get("data_result", {})
                if data_res.get("status") == "not_found":
                    actual_status = "not_found"
            
            actual_route = []
            if route_info.get("needs_policy"):
                actual_route.append("policy")
            if route_info.get("needs_data"):
                actual_route.append("data")
                
            is_route_correct = sorted(actual_route) == sorted(expected_route)
            is_status_correct = actual_status == expected_status
            
            if is_route_correct:
                correct_routes += 1
            if is_status_correct:
                correct_status += 1
                
            results.append({
                "id": case_id,
                "question": question,
                "expected": {
                    "route": expected_route,
                    "status": expected_status
                },
                "actual": {
                    "route": actual_route,
                    "status": actual_status,
                    "final_answer": res.get("final_answer", "")
                },
                "evaluation": {
                    "route_correct": is_route_correct,
                    "status_correct": is_status_correct
                }
            })
            
        total_cases = len(test_cases)
        summary = {
            "total_cases": total_cases,
            "metrics": {
                "route_accuracy": correct_routes / total_cases if total_cases > 0 else 0.0,
                "status_accuracy": correct_status / total_cases if total_cases > 0 else 0.0
            },
            "results": results
        }
        
        summary_path = output_dir / "summary.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
            
        return summary


def build_graph(model: BaseChatModel, store: ShoppingDataStore, policy_store: ChromaPolicyStore, tools: list) -> Any:
    workflow = StateGraph(ShoppingState)
    
    # Add nodes with bound dependencies
    workflow.add_node("supervisor", partial(supervisor_node, model=model))
    workflow.add_node("worker_1_policy", partial(worker_1_policy_node, model=model, policy_store=policy_store))
    workflow.add_node("worker_2_data", partial(worker_2_data_node, model=model, tools=tools))
    workflow.add_node("worker_3_response", partial(worker_3_response_node, model=model))
    
    # Set entry point
    workflow.set_entry_point("supervisor")
    
    # Define routing edge
    workflow.add_conditional_edges(
        "supervisor",
        router,
        {
            "worker_1_policy": "worker_1_policy",
            "worker_2_data": "worker_2_data",
            "worker_3_response": "worker_3_response"
        }
    )
    
    # Join workers at the response node
    workflow.add_edge("worker_1_policy", "worker_3_response")
    workflow.add_edge("worker_2_data", "worker_3_response")
    workflow.add_edge("worker_3_response", END)
    
    return workflow.compile()


def router(state: ShoppingState) -> list[str]:
    route = state.get("route", {})
    status = route.get("status", "ok")
    
    if status == "clarification_needed":
        return ["worker_3_response"]
        
    destinations = []
    if route.get("needs_policy", False):
        destinations.append("worker_1_policy")
    if route.get("needs_data", False):
        destinations.append("worker_2_data")
        
    if not destinations:
        return ["worker_3_response"]
        
    return destinations


def supervisor_node(state: ShoppingState, model: BaseChatModel) -> ShoppingState:
    from app.prompts import SUPERVISOR_PROMPT
    from app.utils import extract_json_payload
    from langchain_core.messages import SystemMessage, HumanMessage
    
    question = state.get("question", "")
    messages = [
        SystemMessage(content=SUPERVISOR_PROMPT),
        HumanMessage(content=question)
    ]
    
    response = model.invoke(messages)
    route_data = extract_json_payload(response.content)
    
    if "status" not in route_data:
        route_data["status"] = "ok"
    if "needs_policy" not in route_data:
        route_data["needs_policy"] = False
    if "needs_data" not in route_data:
        route_data["needs_data"] = False
    if "clarification_question" not in route_data:
        route_data["clarification_question"] = None
    
    # Defensive: clarification_needed must NEVER route to workers
    if route_data["status"] == "clarification_needed":
        route_data["needs_policy"] = False
        route_data["needs_data"] = False
        
    trace_step = {
        "node": "supervisor",
        "timestamp": timestamp_utc(),
        "input": question,
        "output": route_data
    }
    
    return {
        "route": route_data,
        "trace": [trace_step]
    }


def worker_1_policy_node(state: ShoppingState, model: BaseChatModel, policy_store: ChromaPolicyStore) -> ShoppingState:
    from app.prompts import POLICY_WORKER_PROMPT
    from app.utils import extract_json_payload
    from langchain_core.tools import tool
    
    @tool
    def search_policy(query: str) -> str:
        """Tìm kiếm chính sách mua sắm liên quan đến câu hỏi (ví dụ: phí ship, thời gian đổi trả, hoàn tiền, điều kiện voucher)."""
        hits = policy_store.search(query)
        return json.dumps(hits, ensure_ascii=False)
        
    question = state.get("question", "")
    
    from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
    
    messages = [
        SystemMessage(content=POLICY_WORKER_PROMPT),
        HumanMessage(content=question)
    ]
    
    tools = [search_policy]
    tool_map = {t.name: t for t in tools}
    tool_calls_executed = []
    
    for _ in range(5):
        llm_with_tools = model.bind_tools(tools)
        response = llm_with_tools.invoke(messages)
        messages.append(response)
        
        if not response.tool_calls:
            break
            
        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_id = tool_call["id"]
            
            tool_obj = tool_map.get(tool_name)
            if tool_obj:
                try:
                    tool_output = tool_obj.invoke(tool_args)
                except Exception as e:
                    tool_output = json.dumps({"error": str(e)})
            else:
                tool_output = json.dumps({"error": "Tool not found"})
                
            tool_calls_executed.append({
                "tool": tool_name,
                "args": tool_args,
                "output": json.loads(tool_output) if isinstance(tool_output, str) else tool_output
            })
            messages.append(ToolMessage(content=str(tool_output), name=tool_name, tool_call_id=tool_id))
            
    policy_data = extract_json_payload(response.content)
    
    if "status" not in policy_data:
        policy_data["status"] = "ok"
    if "summary" not in policy_data:
        policy_data["summary"] = response.content
    if "facts" not in policy_data:
        policy_data["facts"] = []
    if "citations" not in policy_data:
        policy_data["citations"] = []
        
    trace_step = {
        "node": "worker_1_policy",
        "timestamp": timestamp_utc(),
        "tool_calls": tool_calls_executed,
        "output": policy_data
    }
    
    return {
        "policy_result": policy_data,
        "trace": [trace_step]
    }


def worker_2_data_node(state: ShoppingState, model: BaseChatModel, tools: list) -> ShoppingState:
    from app.prompts import DATA_WORKER_PROMPT
    from app.utils import extract_json_payload
    
    question = state.get("question", "")
    
    from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
    
    messages = [
        SystemMessage(content=DATA_WORKER_PROMPT),
        HumanMessage(content=question)
    ]
    
    tool_map = {t.name: t for t in tools}
    tool_calls_executed = []
    
    for _ in range(5):
        llm_with_tools = model.bind_tools(tools)
        response = llm_with_tools.invoke(messages)
        messages.append(response)
        
        if not response.tool_calls:
            break
            
        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_id = tool_call["id"]
            
            tool_obj = tool_map.get(tool_name)
            if tool_obj:
                try:
                    tool_output = tool_obj.invoke(tool_args)
                except Exception as e:
                    tool_output = {"error": str(e)}
            else:
                tool_output = {"error": "Tool not found"}
                
            tool_calls_executed.append({
                "tool": tool_name,
                "args": tool_args,
                "output": tool_output
            })
            messages.append(ToolMessage(content=json.dumps(tool_output, ensure_ascii=False), name=tool_name, tool_call_id=tool_id))
            
    data_res = extract_json_payload(response.content)
    
    if "status" not in data_res:
        data_res["status"] = "ok"
    if "summary" not in data_res:
        data_res["summary"] = response.content
    if "facts" not in data_res:
        data_res["facts"] = []
    if "missing_fields" not in data_res:
        data_res["missing_fields"] = []
    if "not_found_entities" not in data_res:
        data_res["not_found_entities"] = []
        
    trace_step = {
        "node": "worker_2_data",
        "timestamp": timestamp_utc(),
        "tool_calls": tool_calls_executed,
        "output": data_res
    }
    
    return {
        "data_result": data_res,
        "trace": [trace_step]
    }


def worker_3_response_node(state: ShoppingState, model: BaseChatModel) -> ShoppingState:
    from app.prompts import RESPONSE_WORKER_PROMPT
    from langchain_core.messages import SystemMessage, HumanMessage
    
    supervisor_route = state.get("route", {})
    policy_res = state.get("policy_result", {})
    data_res = state.get("data_result", {})
    question = state.get("question", "")
    
    context = {
        "question": question,
        "route": supervisor_route,
        "policy_result": policy_res,
        "data_result": data_res
    }
    
    messages = [
        SystemMessage(content=RESPONSE_WORKER_PROMPT),
        HumanMessage(content=json.dumps(context, ensure_ascii=False))
    ]
    
    response = model.invoke(messages)
    final_ans = response.content.strip()
    
    trace_step = {
        "node": "worker_3_response",
        "timestamp": timestamp_utc(),
        "output": final_ans
    }
    
    return {
        "final_answer": final_ans,
        "trace": [trace_step]
    }
