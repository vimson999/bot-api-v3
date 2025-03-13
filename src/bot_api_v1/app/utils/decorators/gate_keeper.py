import logging
from functools import wraps
from typing import Callable, Any, Optional

from bot_api_v1.app.core.logger import logger
from bot_api_v1.app.core.context import request_ctx


class GateKeeperError(Exception):
    """Gate Keeper 专用异常类"""
    pass

def gate_keeper(
    base_tollgate: Optional[str] = None,
    strict_mode: bool = True
) -> Callable:
    """
    生产级别的tollgate管理装饰器

    Args:
        base_tollgate (str, optional): 基础tollgate值。默认为None，将自动推断。
        strict_mode (bool, optional): 是否启用严格模式。默认为True。
            严格模式下，将对tollgate的处理更加严格。

    Raises:
        GateKeeperError: 在tollgate处理过程中出现的异常

    Returns:
        Callable: 装饰后的函数
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                ctx = request_ctx.get_context()

                # 处理base_tollgate
                if base_tollgate is None:
                    current_base = ctx.get(
                        'base_tollgate', 
                        ctx.get('tollgate', '20').split('-')[0]
                    )
                else:
                    current_base = base_tollgate

                # 获取当前tollgate
                current_tollgate = ctx.get('current_tollgate', '1')

                # 验证当前tollgate
                try:
                    int_current_tollgate = int(current_tollgate)
                except ValueError:
                    if strict_mode:
                        raise GateKeeperError(f"Invalid tollgate value: {current_tollgate}")
                    int_current_tollgate = 1

                # 递增tollgate
                new_tollgate = str(int_current_tollgate + 1)

                # 更新上下文
                ctx['base_tollgate'] = current_base
                ctx['current_tollgate'] = new_tollgate
                request_ctx.set_context(ctx)

                # 日志记录
                logger.info(
                    f"Gate Keeper: "
                    f"base_tollgate={current_base}, "
                    f"current_tollgate={current_tollgate}, "
                    f"new_tollgate={new_tollgate}"
                )

                # 执行原始方法
                return func(*args, **kwargs)

            except Exception as e:
                # 详细的异常处理
                logger.error(
                    f"Gate Keeper Error in {func.__name__}: {str(e)}",
                    exc_info=True
                )
                
                # 在严格模式下抛出异常
                if strict_mode:
                    raise GateKeeperError(f"Gate Keeper failed: {str(e)}") from e
                
                # 非严格模式下返回原始方法调用
                return func(*args, **kwargs)

        return wrapper
    return decorator