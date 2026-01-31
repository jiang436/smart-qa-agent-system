"""Rebuild FAQ JSON files with guaranteed valid JSON output."""
import json
import re
import sys


def sanitize(text: str) -> str:
    """Replace all inner double quotes with Chinese corner brackets."""
    # Replace smart/curly quotes if any
    text = text.replace("“", "「")  # " -> 「
    text = text.replace("”", "」")  # " -> 」
    text = text.replace("‘", "「")  # ' -> 「
    text = text.replace("’", "」")  # ' -> 」

    # Replace ASCII double quotes used as Chinese punctuation
    # Pattern: CJK char + " + CJK/non-space -> replace " with 「 or 」
    # We'll be conservative: if " is between CJK chars, it's a content quote

    # Remove all remaining ASCII double quotes that could be content quotes
    # by checking context. Structural quotes will be re-added by json.dumps.

    # Strategy: find pairs of " that look like Chinese quotation
    # text"quoted"text -> text「quoted」text
    changed = True
    while changed:
        changed = False
        # Match: CJK/punct + " + non-" chars + " + CJK/punct
        m = re.search(
            r'([一-鿿　-〿＀-￯，。、：；？！～）】」』])"'
            r'([^"]{1,80})'
            r'"([一-鿿　-〿＀-￯，。、：；？！～（【「『])',
            text,
        )
        if m:
            text = text[: m.start()] + m.group(1) + "「" + m.group(2) + "」" + m.group(3) + text[m.end():]
            changed = True

    # Also handle quotes at start/end of string or after punctuation
    # ,"text" -> ,「text」
    text = re.sub(
        r'([，。、：；？！～）】」』　])"([^"]{1,60})"',
        r'\1「\2」',
        text,
    )

    return text


def rebuild_file(filepath: str):
    """Try to read a broken JSON file, extract Q&A data, and rebuild."""
    with open(filepath, "r", encoding="utf-8") as f:
        raw = f.read()

    # Try to extract individual Q&A entries using regex
    # Match patterns like: {"id": "XX-001", "question": "...", "answer": "..."}
    # Even if JSON is broken, the id/question/answer structure should be recoverable

    entries = []

    # Find all id patterns
    id_pattern = re.compile(r'"id":\s*"([^"]+)"')
    ids = id_pattern.findall(raw)

    # Find question and answer using broader patterns
    # We'll extract each object by finding { ... } blocks
    # Split by looking for "id": "XX-NNN" as block markers

    blocks = re.split(r'\n\s*\n', raw)

    for block in blocks:
        block = block.strip()
        if not block or block in ('[', ']'):
            continue

        # Extract id
        id_match = re.search(r'"id":\s*"([^"]+)"', block)
        if not id_match:
            continue
        qid = id_match.group(1)

        # Extract question - everything between "question": " and next structural marker
        q_match = re.search(r'"question":\s*"([^"]*)"', block)
        if not q_match:
            continue
        question = q_match.group(1)

        # Extract answer - everything between "answer": " and the closing "},
        # This is trickier because answer contains inner quotes
        a_match = re.search(r'"answer":\s*"(.*)"\s*\}', block, re.DOTALL)
        if a_match:
            answer = a_match.group(1)
        else:
            # Try alternative: find "answer": " then everything until "} at line end
            a_start = block.find('"answer": "')
            if a_start >= 0:
                a_start += len('"answer": "')
                # Find the last "} or ",
                rest = block[a_start:]
                # Remove trailing "}, or ",
                if rest.endswith('"},'):
                    rest = rest[:-3]
                elif rest.endswith('"}'):
                    rest = rest[:-2]
                elif rest.endswith('"'):
                    rest = rest[:-1]
                answer = rest
            else:
                continue

        # Sanitize question and answer
        question = sanitize(question)
        answer = sanitize(answer)

        entries.append({"id": qid, "question": question, "answer": answer})

    if not entries:
        print(f"  WARNING: Could not extract any entries from {filepath}")
        return False

    print(f"  Extracted {len(entries)} entries from {filepath}")

    # Write as valid JSON
    json_str = json.dumps(entries, ensure_ascii=False, indent=2)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(json_str)

    # Validate
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(f"  {filepath}: {len(data)} questions - VALID JSON")
        return True
    except json.JSONDecodeError as e:
        print(f"  {filepath}: FAILED validation - {e}")
        return False


if __name__ == "__main__":
    files = [
        "data/faq_knowledge_base.json",
        "data/faq_consumables.json",
        "data/faq_troubleshooting.json",
    ]
    for f in files:
        rebuild_file(f)
