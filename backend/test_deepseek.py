import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.services.deepseek_client import chat

result = chat("请用一句话介绍成都3日游的亮点")
print(result)