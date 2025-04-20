#!/bin/bash

# 脚本出错时立即退出
set -e

echo "Setting up project environment..."

# 激活虚拟环境 (如果需要，路径可能不同)
# source /path/to/your/project/.venv/bin/activate

# 确保 pip 是最新的 (可选但推荐)
pip install --upgrade pip

echo "Installing CPU-only PyTorch..."
# 使用从 PyTorch 官网获取的针对 Linux + CPU 的命令
pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
# 或者官网推荐的标准命令

echo "Installing OpenAI Whisper and other requirements..."
pip install openai-whisper
# 如果有 requirements.txt，确保 torch 相关行被注释掉或版本匹配
# pip install -r requirements.txt

echo "Setup complete!"

# 在这里可以添加启动你的 Python 程序的命令
# python your_app.py