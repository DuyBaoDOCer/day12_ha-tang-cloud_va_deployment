from __future__ import annotations


def parse_policy_markdown(markdown_text: str) -> list[dict]:
    chunks = []
    lines = markdown_text.splitlines()
    
    current_h2 = ""
    current_h3 = ""
    current_content = []
    
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            # If we were tracking a previous H3, save it
            if current_h2 and current_h3:
                content_str = "\n".join(current_content).strip()
                chunks.append({
                    "section_h2": current_h2,
                    "section_h3": current_h3,
                    "citation": f"{current_h2} > {current_h3}",
                    "rendered_text": f"## {current_h2}\n### {current_h3}\n{content_str}"
                })
            current_h2 = stripped[3:].strip()
            current_h3 = ""
            current_content = []
        elif stripped.startswith("### "):
            # If we were tracking a previous H3, save it
            if current_h2 and current_h3:
                content_str = "\n".join(current_content).strip()
                chunks.append({
                    "section_h2": current_h2,
                    "section_h3": current_h3,
                    "citation": f"{current_h2} > {current_h3}",
                    "rendered_text": f"## {current_h2}\n### {current_h3}\n{content_str}"
                })
            current_h3 = stripped[4:].strip()
            current_content = []
        else:
            # It's content line, append it if we are inside an H3
            if current_h2 and current_h3:
                current_content.append(line)
                
    # Don't forget the last chunk
    if current_h2 and current_h3:
        content_str = "\n".join(current_content).strip()
        chunks.append({
            "section_h2": current_h2,
            "section_h3": current_h3,
            "citation": f"{current_h2} > {current_h3}",
            "rendered_text": f"## {current_h2}\n### {current_h3}\n{content_str}"
        })
        
    return chunks
