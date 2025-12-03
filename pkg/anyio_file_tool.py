import os
from pathlib import Path

import anyio
import pandas as pd
from async_lru import alru_cache


class AnyioFile:

    def __init__(self, file_path: str | Path):
        if isinstance(file_path, Path):
            file_path = file_path.as_posix()

        self.file_path: str = file_path
        self.anyio_path: anyio.Path = anyio.Path(file_path)

    async def unlink(self):
        """
        删除文件。

        参数:
            file_path (str): 要删除的文件路径。

        异常:
            FileNotFoundError: 如果文件不存在。
        """

        if not await self.anyio_path.exists():
            return

        await self.anyio_path.unlink()

    async def exists(self) -> bool:
        """
        检查文件是否存在。

        参数:
            file_path (str): 要检查的文件路径。

        返回:
            bool: 文件是否存在。
        """

        return await self.anyio_path.exists()

    async def stat(self) -> os.stat_result:
        """
        获取文件信息。

        参数:
            file_path (str): 要获取文件信息的文件路径。

        返回:
            anyio.StatInfo: 文件信息。
        """
        stat_result = await self.anyio_path.stat()
        return stat_result

    async def mkdir(self, parents: bool = False, exist_ok: bool = False):
        """
        创建目录。

        参数:
            file_path (str): 要创建的目录路径。

        异常:
            FileExistsError: 如果目录已经存在。
        """

        await self.anyio_path.mkdir(parents=parents, exist_ok=exist_ok)

    async def read(self, mode: str = "r", encoding: str | None = "utf-8") -> str | bytes:
        """
        读取完整文件内容并返回。
        - 文本模式（默认 "r"）：返回 str（需 encoding）
        - 二进制模式（包含 'b'）：返回 bytes（忽略 encoding）
        """
        if "b" in mode:
            async with await self.anyio_path.open(mode=mode) as f:
                return await f.read()
        else:
            async with await self.anyio_path.open(mode=mode, encoding=encoding) as f:
                return await f.read()

    async def read_excel_with_pandas(
            self,
            *,
            sheet_name: int | str | None = 0,  # 0 / 名称 / 列表 / None
            dtype=None,
            engine=None,  # None=自动，或 "openpyxl"、"xlrd"（.xls）等
    ) -> pd.DataFrame:
        # 整个解析过程是同步的；放线程池里跑，避免阻塞事件循环
        def _read_excel():
            return pd.read_excel(self.file_path, sheet_name=sheet_name, dtype=dtype, engine=engine)

        return await anyio.to_thread.run_sync(_read_excel)

    async def write(
            self,
            data: str | bytes,
            mode: str = "w",
            encoding: str | None = "utf-8",
            ensure_parent: bool = True,
            flush: bool = False,
    ) -> int:
        """
        写入数据（返回写入的字节数/字符数，取决于底层实现）。
        - 二进制模式（含 'b'）传 bytes；文本模式传 str
        - ensure_parent=True：自动创建父目录
        - flush=True：写完后显式 flush（一般不必）
        """
        if ensure_parent:
            await self.anyio_path.parent.mkdir(parents=True, exist_ok=True)

        if "b" in mode:
            if not isinstance(data, (bytes, bytearray, memoryview)):
                raise TypeError("binary mode requires bytes-like 'data'")
            async with await self.anyio_path.open(mode=mode) as f:
                n = await f.write(data)
                if flush:
                    await f.flush()
                return n
        else:
            if not isinstance(data, str):
                raise TypeError("text mode requires 'str' data")
            async with await self.anyio_path.open(mode=mode, encoding=encoding) as f:
                n = await f.write(data)
                if flush:
                    await f.flush()
                return n


@alru_cache(maxsize=128, ttl=60)
def new_anyio_file(file_path: str | Path) -> AnyioFile:
    """
    创建一个新的 AnyioFile 对象。

    参数:
        file_path (str): 文件路径。

    返回:
        AnyioFile: 新的 AnyioFile 对象。
    """

    return AnyioFile(file_path)
