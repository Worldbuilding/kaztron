def format_list(list_) -> str:
    """
    Format a list as a string for display over Discord, with indices starting from 1.
    """
    fmt = "{0: >3d}. {1:s}"
    text_bits = ["```"]
    text_bits.extend(fmt.format(i+1, item) for i, item in enumerate(list_))
    text_bits.append("```")
    return '\n'.join(text_bits)
