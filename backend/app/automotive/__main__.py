"""Run: python -m app.automotive [--input crm.json] [--sample]. No network writes."""
import argparse
import json
from pathlib import Path
from fastapi.encoders import jsonable_encoder
from app.automotive.pilot import PreviewRequest, demo_data, preview


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path)
    parser.add_argument('--sample', action='store_true', help='Print sample CRM input')
    args = parser.parse_args()
    data = PreviewRequest.model_validate_json(args.input.read_text()) if args.input else demo_data()
    print(json.dumps(jsonable_encoder(data if args.sample else preview(data)), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
