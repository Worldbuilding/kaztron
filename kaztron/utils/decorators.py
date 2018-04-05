import asyncio
import functools


# noinspection PyPep8Naming
def error_handler(ErrorType, return_value):
    """
    Decorator: handles a specified error, returning a constant return_value if that error is raised
    in executing the function.
    """
    def decorator(f):
        def deco_f(*args, **kwargs):
            try:
                return f(*args, **kwargs)
            except ErrorType:
                return return_value
        return deco_f
    return decorator


def task_handled_errors(func):
    """
    Decorator for custom tasks. Can *only* wrap coroutines. Any raised exceptions will call the
    KazTron general error handler.
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        # noinspection PyBroadException
        try:
            return await func(*args, **kwargs)
        except asyncio.CancelledError:
            raise
        except Exception:
            core_cog = args[0].bot.get_cog("CoreCog")
            await core_cog.on_error(func.__name__)
    return wrapper
