"""
测试用例模板
"""
import logging
import sys

import pytest

logger = logging.getLogger(__name__)

"""
具体测试内容
"""

if __name__ == "__main__":
    # 允许直接运行此文件调试
    sys.exit(pytest.main(["-s", "-v", "--log-cli-level=INFO", __file__]))
