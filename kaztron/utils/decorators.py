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
