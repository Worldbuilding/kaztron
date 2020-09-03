import asyncio
import functools


def error_handler(ErrorType, return_value):
    """
    Decorator: handles a specified error, returning a constant return_value if that error is raised
    in executing the function.
    """
    def decorator(f):
        @functools.wraps(f)
        def deco_f(*args, **kwargs):
            try:
                return f(*args, **kwargs)
            except ErrorType:
                return return_value
        return deco_f
    return decorator


def natural_truncate(max_len, ellipsis_='[...]'):
    """
    Natural truncation decorator. Truncate the return value (string only) to the length specified,
    along a word boundary, assuming the string is natural language.
    :param max_len: Maximum length to allow.
    :param ellipsis_: The ellipsis text to show when truncated.
    :return:
    """
    # noinspection PyPep8Naming
    from kaztron.utils import strings

    def decorator(f):
        @functools.wraps(f)
        def deco_f(*args, **kwargs):
            return strings.natural_truncate(f(*args, **kwargs), max_len, ellipsis_)
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
        except (asyncio.CancelledError, KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            await args[0].core.on_error(func.__name__)
    return wrapper
