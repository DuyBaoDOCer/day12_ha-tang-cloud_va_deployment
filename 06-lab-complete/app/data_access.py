from __future__ import annotations

from pathlib import Path
from typing import Any


import json
from langchain_core.tools import tool


class ShoppingDataStore:
    """Mock-data lookup class with indexes for fast retrieval."""

    def __init__(self, json_path: Path) -> None:
        if not json_path.exists():
            raise FileNotFoundError(f"Mock data file not found at {json_path}")
            
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        self.metadata = data.get("metadata", {})
        self.customers = data.get("customers", [])
        self.orders = data.get("orders", [])
        self.vouchers = data.get("vouchers", [])

        # Build indexes for fast lookup
        self.customer_by_id = {c["customer_id"]: c for c in self.customers}
        self.order_by_id = {o["order_id"]: o for o in self.orders}

        self.orders_by_customer_id = {}
        for o in self.orders:
            c_id = o.get("customer_id")
            if c_id:
                if c_id not in self.orders_by_customer_id:
                    self.orders_by_customer_id[c_id] = []
                self.orders_by_customer_id[c_id].append(o)

        self.vouchers_by_customer_id = {}
        for v in self.vouchers:
            c_id = v.get("customer_id")
            if c_id:
                if c_id not in self.vouchers_by_customer_id:
                    self.vouchers_by_customer_id[c_id] = []
                self.vouchers_by_customer_id[c_id].append(v)

    def get_customer_by_id(self, customer_id: str) -> dict[str, Any]:
        c_id = str(customer_id).strip()
        customer = self.customer_by_id.get(c_id)
        if customer:
            return {"status": "ok", "customer": customer}
        return {"status": "not_found", "customer_id": c_id}

    def get_orders_by_customer_id(self, customer_id: str, limit: int = 10) -> dict[str, Any]:
        c_id = str(customer_id).strip()
        if c_id not in self.customer_by_id:
            return {"status": "not_found", "customer_id": c_id}
        orders = self.orders_by_customer_id.get(c_id, [])
        # Sort by created_at descending if available
        sorted_orders = sorted(orders, key=lambda x: x.get("created_at", ""), reverse=True)
        return {"status": "ok", "orders": sorted_orders[:limit]}

    def get_order_detail_by_order_id(self, order_id: str) -> dict[str, Any]:
        o_id = str(order_id).strip()
        order = self.order_by_id.get(o_id)
        if order:
            return {"status": "ok", "order": order}
        return {"status": "not_found", "order_id": o_id}

    def get_vouchers_by_customer_id(
        self,
        customer_id: str,
        only_active: bool = False,
    ) -> dict[str, Any]:
        c_id = str(customer_id).strip()
        if c_id not in self.customer_by_id:
            return {"status": "not_found", "customer_id": c_id}
        vouchers = self.vouchers_by_customer_id.get(c_id, [])
        if only_active:
            # Filter to keep only active/restored vouchers with remaining uses
            vouchers = [
                v for v in vouchers 
                if v.get("status") in ("active", "restored") and v.get("remaining_uses", 0) > 0
            ]
        return {"status": "ok", "vouchers": vouchers}


def build_data_tools(store: ShoppingDataStore) -> list:
    @tool
    def get_customer_by_id(customer_id: str) -> dict[str, Any]:
        """Tra cứu thông tin chi tiết của khách hàng bằng mã khách hàng (ví dụ: C001, C002).
        Trả về hạng thành viên (tier), quota voucher, và thông tin tài khoản.
        """
        return store.get_customer_by_id(customer_id)

    @tool
    def get_orders_by_customer_id(customer_id: str) -> dict[str, Any]:
        """Tra cứu danh sách các đơn hàng gần đây của khách hàng bằng mã khách hàng (customer_id).
        Hữu ích khi cần biết khách hàng có những đơn hàng nào.
        """
        return store.get_orders_by_customer_id(customer_id)

    @tool
    def get_order_detail_by_order_id(order_id: str) -> dict[str, Any]:
        """Tra cứu chi tiết một đơn hàng cụ thể bằng mã đơn hàng (order_id, ví dụ: 1971, 2058).
        Trả về trạng thái đơn hàng (order_status), ngày dự kiến giao, hạn chót đổi trả, và danh sách sản phẩm.
        """
        return store.get_order_detail_by_order_id(order_id)

    @tool
    def get_vouchers_by_customer_id(customer_id: str) -> dict[str, Any]:
        """Tra cứu toàn bộ danh sách voucher khuyến mãi của một khách hàng bằng mã khách hàng (customer_id).
        Trả về trạng thái voucher (active, used, expired), giá trị giảm giá, và điều kiện áp dụng.
        """
        return store.get_vouchers_by_customer_id(customer_id)

    return [
        get_customer_by_id,
        get_orders_by_customer_id,
        get_order_detail_by_order_id,
        get_vouchers_by_customer_id,
    ]
