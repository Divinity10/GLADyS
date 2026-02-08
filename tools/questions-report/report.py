import os
import re
import sys
import json
import argparse
from datetime import datetime, date, timedelta
from pathlib import Path

def parse_date(date_str):
    try:
        # Match YYYY-MM-DD
        match = re.search(r"(\d{4})-(\d{2})-(\d{2})", date_str)
        if match:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        pass
    return None

def is_migrated(text):
    # ADR-XXXX
    if re.search(r"ADR-\d+", text):
        return True
    # see {doc}
    if "see {" in text and "}" in text:
        return True
    # Markdown link [text](link.md)
    if re.search(r"\[.*?\]\(.*?\.(md|MD)\)", text):
        return True
    return False

def scan_questions(questions_dir, stale_threshold_days=30):
    report_data = {
        "files": [],
        "migration_candidates": [],
        "stale_questions": []
    }
    
    today = date.today()
    stale_threshold = today - timedelta(days=stale_threshold_days)
    
    # Sort files for consistent output
    files = sorted(Path(questions_dir).glob("*.md"))
    
    for file_path in files:
        if file_path.name.lower() == "readme.md":
            continue
            
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        file_stats = {
            "path": str(file_path),
            "name": file_path.name,
            "open": 0,
            "partial": 0,
            "resolved": 0
        }
        
        # Split into Open and Resolved sections
        sections = re.split(r"^##\s+", content, flags=re.MULTILINE)
        
        for section in sections:
            if section.startswith("Open Questions"):
                # Split by ### Q:
                entries = re.split(r"^###\s+Q:", section, flags=re.MULTILINE)[1:]
                for entry in entries:
                    lines = entry.splitlines()
                    title = lines[0].strip() if lines else "Untitled"
                    
                    # Extract status
                    status_match = re.search(r"\*\*Status\*\*:\s*([^\n]+)", entry, re.IGNORECASE)
                    status_text = status_match.group(1).strip() if status_match else "Open"
                    
                    if "Partial" in status_text:
                        file_stats["partial"] += 1
                    elif "Resolved" in status_text:
                        file_stats["resolved"] += 1
                    else:
                        # "Open" or "In Progress"
                        file_stats["open"] += 1
                        
                        # Check staleness for Open/In Progress
                        created_match = re.search(r"\*\*Created\*\*:\s*([^\n]+)", entry, re.IGNORECASE)
                        if created_match:
                            created_date = parse_date(created_match.group(1))
                            if created_date and created_date < stale_threshold:
                                report_data["stale_questions"].append({
                                    "file": str(file_path),
                                    "title": f"Q: {title}",
                                    "created": created_date.isoformat()
                                })
                                
            elif section.startswith("Resolved"):
                # Split by ### R:
                entries = re.split(r"^###\s+R:", section, flags=re.MULTILINE)[1:]
                for entry in entries:
                    file_stats["resolved"] += 1
                    lines = entry.splitlines()
                    title = lines[0].strip() if lines else "Untitled"
                    
                    # Check for migration
                    if not is_migrated(entry):
                        report_data["migration_candidates"].append({
                            "file": str(file_path),
                            "title": f"R: {title}"
                        })
                        
        report_data["files"].append(file_stats)
        
    return report_data

def print_text_report(data):
    print("Design Questions Status Report")
    print("==============================")
    print()
    
    # Summary Table
    print(f"{'File':<30} | {'Open':<5} | {'Partial':<7} | {'Resolved':<8}")
    print("-" * 60)
    for f in data["files"]:
        print(f"{f['name']:<30} | {f['open']:<5} | {f['partial']:<7} | {f['resolved']:<8}")
    print()
    
    # Migration Candidates
    if data["migration_candidates"]:
        print("Migration Candidates (Resolved but not migrated)")
        print("-----------------------------------------------")
        for mc in data["migration_candidates"]:
            print(f"- {mc['file']}: {mc['title']}")
        print()
        
    # Stale Questions
    if data["stale_questions"]:
        print("Stale Open Questions (> 30 days old)")
        print("------------------------------------")
        for sq in data["stale_questions"]:
            print(f"- {sq['file']}: {sq['title']} (Created: {sq['created']})")
        print()

def main():
    parser = argparse.ArgumentParser(description="Report status of design questions")
    parser.add_argument("--dir", default="docs/design/questions", help="Directory containing question files")
    parser.add_argument("--json", action="store_true", help="Output in JSON format")
    parser.add_argument("--stale-days", type=int, default=30, help="Days until an open question is considered stale")
    args = parser.parse_args()
    
    if not os.path.exists(args.dir):
        print(f"Error: Directory {args.dir} does not exist.")
        sys.exit(1)
        
    data = scan_questions(args.dir, args.stale_days)
    
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print_text_report(data)

if __name__ == "__main__":
    main()
