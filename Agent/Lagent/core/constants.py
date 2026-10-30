"""核心常量定义。

仅存放与业务无关的基础常量，供 core 各层引用，避免魔法数字散落各处。
"""

# readFile 允许读取的单文件体积上限（1 MB）。
MAX_TEXT_SIZE = 1024 * 1024

# RunCil 执行本地命令的超时时间（秒）。
COMMAND_TIMEOUT = 30

# RunCil 单次返回的 stdout / stderr 各自的最大字符数，超出则截断。
MAX_COMMAND_OUTPUT = 4 * 1024
