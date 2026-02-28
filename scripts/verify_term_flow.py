
import json
import sys

def verify_flow(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error loading JSON: {e}")
        return

    print(f"Loaded {len(data)} items.")

    for i, item in enumerate(data):
        print(f"\n--- Item {i+1} ---")
        parsed = item.get("parsed", {})
        if not parsed:
            print("No 'parsed' field found.")
            continue

        # 1. Extract Concepts (Terms)
        concepts = parsed.get("概念", {})
        terms = set()
        
        # Main discipline terms
        main_concepts = concepts.get("主学科", [])
        if main_concepts:
            for c in main_concepts:
                if isinstance(c, dict):
                    t = c.get("term")
                    n = c.get("normalized")
                    if t: terms.add(t)
                    if n: terms.add(n)
        
        # Secondary discipline terms
        sec_concepts = concepts.get("辅学科", {})
        if isinstance(sec_concepts, dict):
            for cat, c_list in sec_concepts.items():
                for c in c_list:
                    if isinstance(c, dict):
                        t = c.get("term")
                        n = c.get("normalized")
                        if t: terms.add(t)
                        if n: terms.add(n)
        
        print(f"Total Extracted Terms (Concept Pool): {len(terms)}")
        # print(f"Example Terms: {list(terms)[:5]}")

        # 2. Extract Hypothesis Nodes
        # Check if '假设' exists in parsed
        hypotheses = parsed.get("假设", {})
        if not hypotheses:
            print("'假设' not found in parsed data. Checking raw string...")
            # Fallback: Try to find it in 'raw' string if parsed is incomplete?
            # But usually 'parsed' should have it if 'ok' is true.
            pass
        
        hyp_nodes = set()
        hyp_relations = []
        
        for level in ["一级", "二级", "三级"]:
            paths = hypotheses.get(level, [])
            if not paths:
                continue
            for path in paths:
                for step in path:
                    if isinstance(step, dict):
                        h = step.get("head")
                        t = step.get("tail")
                        r = step.get("relation")
                        if h: hyp_nodes.add(h)
                        if t: hyp_nodes.add(t)
                        if h and t and r:
                            hyp_relations.append(f"{h} --[{r}]--> {t}")

        print(f"Total Hypothesis Nodes: {len(hyp_nodes)}")
        
        # 3. Verify Overlap
        found_in_concepts = 0
        missing_nodes = []
        
        for node in hyp_nodes:
            # Flexible matching: exact match or partial match
            # The prompt says "尽量使用...term or normalized"
            if node in terms:
                found_in_concepts += 1
            else:
                # Try simple normalization (lowercase, etc) just in case
                # But here we stick to exact string match for strict verification
                missing_nodes.append(node)
        
        if hyp_nodes:
            match_rate = (found_in_concepts / len(hyp_nodes)) * 100
            print(f"Match Rate (Hypothesis Nodes found in Concept Pool): {match_rate:.2f}% ({found_in_concepts}/{len(hyp_nodes)})")
        else:
            print("No hypothesis nodes found.")

        if missing_nodes:
            print(f"Sample Missing Nodes (not exact match in concepts): {missing_nodes[:5]}")
            
        if hyp_relations:
            print(f"Sample Hypothesis Path Step: {hyp_relations[0]}")
            parts = hyp_relations[0].split(" --[")
            if len(parts) > 0:
                h_node = parts[0]
                print(f"Tracing Node '{h_node}': Found in Concepts? {'YES' if h_node in terms else 'NO'}")

if __name__ == "__main__":
    verify_flow("/ssd/wangyuyang/git/yanzhi/result_no_cs_nc_down_24.json")
