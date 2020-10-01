from typing import List

from discord.embeds import Embed, EmptyEmbed

from kaztron.utils.discord import Limits
from kaztron.utils.strings import natural_truncate


class EmbedSplitter:
    """
    Embed generator that splits embeds and fields according to the Discord embed limits.

    The constructor takes any keyword arguments that :cls:`discord.Embed`'s constructor can take.
    You can set certain further properties of the Embed using `set_*` methods similar to Embed's
    own, but this should be done *before* starting to add fields.

    You can read Embed properties (other than fields) set on this Embed by accessing the
    :cls:`discord.Embed` instance :attr:`~.truncate`. You should not write properties to it
    (use this class's `set_*` methods or the constructor for that).

    :param auto_truncate: If True, automatically truncate title, description, etc. fields. If not,
        raise a ValueError if a value exceeds the limit.
    :raise ValueError: a text value is too long
    """
    def __init__(self, *,
                 auto_truncate=False, repeat_header=True, repeat_footer=False, repeat_image=True,
                 title=EmptyEmbed, description=EmptyEmbed,
                 **kwargs):
        kwargs = kwargs.copy()
        self.auto_truncate = auto_truncate
        self._embeds = []
        self._field_cache = []
        self.template = None
        self.repeat_header = repeat_header
        self.repeat_footer = repeat_footer
        self.repeat_image = repeat_image
        self.cur_num_fields = 0

        if title is not EmptyEmbed and len(title) > Limits.EMBED_TITLE:
            if not self.auto_truncate:
                raise ValueError("Title too long")
            title = natural_truncate(title, maxlen=Limits.EMBED_TITLE)

        if description is not EmptyEmbed and len(description) > Limits.EMBED_DESC:
            if not self.auto_truncate:
                raise ValueError("Description too long")
            description = natural_truncate(description, maxlen=Limits.EMBED_DESC)

        self.template = Embed(title=title, description=description, **kwargs)
        self._cur_embed = None

    @property
    def cur_embed(self):
        if self._cur_embed is None:
            self._start_initial_embed()
        return self._cur_embed

    @cur_embed.setter
    def cur_embed(self, v):
        self._cur_embed = v

    def set_author(self, *, name: str, url: str=EmptyEmbed, icon_url: str=EmptyEmbed):
        if len(name) > Limits.EMBED_AUTHOR:
            if not self.auto_truncate:
                raise ValueError("Author too long")
            name = natural_truncate(name, maxlen=Limits.EMBED_AUTHOR)
        self.template.set_author(name=name, url=url, icon_url=icon_url)

    def set_footer(self, *, text: str=EmptyEmbed, icon_url: str=EmptyEmbed):
        if len(text) > Limits.EMBED_FOOTER:
            if not self.auto_truncate:
                raise ValueError("Footer too long")
            text = natural_truncate(text, maxlen=Limits.EMBED_FOOTER)
        self.template.set_footer(text=text, icon_url=icon_url)

    def set_image(self, *, url: str):
        self.template.set_image(url=url)

    def set_thumbnail(self, *, url: str):
        self.template.set_thumbnail(url=url)

    def add_field(self, *, name, value, inline=True):
        """
        Add field to the embed(s). This method allows for breaking (splitting) into a new embed
        AFTER this new field.

        A field value that exceeds the max length will split the field if auto_truncate is
        enabled, or raise a ValueError otherwise.

        :raise ValueError: Field name or value too long (and auto_truncate disabled)
        """
        self.add_field_no_break(name=name, value=value, inline=inline)
        self._flush_field_cache()

    def add_field_no_break(self, *, name, value, inline=True):
        """
        Add field to the embed(s). This method does not allow for breaking (splitting) into a new
        embed AFTER this new field (it may allow it before, if :meth:`~.add_field` was used).

        A field value that exceeds the max length will split the field if auto_truncate is
        enabled, or raise a ValueError otherwise.

        :raise ValueError: Field name or value too long (and auto_truncate disabled)
        """
        if len(name) > Limits.EMBED_FIELD_NAME:
            if not self.auto_truncate:
                raise ValueError("Field name too long")
            name = natural_truncate(name, maxlen=Limits.EMBED_FIELD_NAME)
        elif not name.strip():
            raise ValueError("Empty name field for embed titled {!r}".format(self.template.title))

        if len(value) > Limits.EMBED_FIELD_VALUE:
            if not self.auto_truncate:
                raise ValueError("Field value too long")
            self._add_split_field(name, value, inline)
        elif not value.strip():
            raise ValueError("Empty value for field named {!r}".format(name))
        else:
            self._field_cache.append({'name': name, 'value': value, 'inline': inline})

        cur_len = sum(len(f['name']) + len(f['value']) for f in self._field_cache)
        try:
            if not self.repeat_footer:  # always reserve footer space, just 'cause it's simpler
                cur_len += len(self.template.footer.text)
        except TypeError:  # self.template.footer.text is EmptyEmbed
            pass

        # if the current field cache does not fit, make new embed
        # cache is not flushed into the embed, so this will keep currently cached fields together
        if self._is_too_long(cur_len) or self._num_fields() > Limits.EMBED_FIELD_NUM:
            self._start_new_embed()

    def _add_split_field(self, name, value, inline):
        """ Split a field into multiple fields if the value is too long. """
        value_rem = value
        while value_rem:
            # add current field
            new_val = natural_truncate(
                value_rem, maxlen=Limits.EMBED_FIELD_VALUE, ellipsis_=''
            )
            self._field_cache.append({'name': name, 'value': new_val, 'inline': inline})

            # next iter
            value_rem = value_rem[len(new_val):]
            name = '…'

    def _start_initial_embed(self):
        self.cur_embed = self._make_embed_skeleton(
            header=True, desc=True, footer=self.repeat_footer, image=True
        )
        self.cur_num_fields = 0
        self._embeds.append(self.cur_embed)

    def _start_new_embed(self):
        self.cur_embed = self._make_embed_skeleton(
            desc=False, header=self.repeat_header,
            footer=self.repeat_footer, image=self.repeat_image
        )
        self.cur_num_fields = 0
        self._embeds.append(self.cur_embed)

    def _flush_field_cache(self):
        for field in self._field_cache:
            self.cur_embed.add_field(**field)
        self.cur_num_fields += len(self._field_cache)
        self._field_cache.clear()

    def _is_too_long(self, new_length=0):
        """ Check if current embed would be too long with ``new_length`` characters added to it. """
        return get_embed_size(self.cur_embed) + new_length > Limits.EMBED_TOTAL

    def _num_fields(self):
        """ Check number of fields of the current embed, including cached fields. """
        return self.cur_num_fields + len(self._field_cache)

    def _make_embed_skeleton(self, header: bool, desc: bool, footer: bool, image: bool):
        embed = self.template
        e_new = Embed(colour=embed.colour, type=embed.type)
        if header:
            e_new.title = embed.title
            e_new.url = embed.url
            author = embed.author
            if author.name is not EmptyEmbed:
                e_new.set_author(name=author.name, url=author.url, icon_url=author.icon_url)
        if desc:
            e_new.description = embed.description
        if image:
            if embed.image.url is not EmptyEmbed:
                e_new.set_image(url=embed.image.url)
            if embed.thumbnail.url is not EmptyEmbed:
                e_new.set_thumbnail(url=embed.thumbnail.url)
        if footer:
            e_new.timestamp = embed.timestamp
            footer = embed.footer
            e_new.set_footer(text=footer.text, icon_url=footer.icon_url)
        return e_new

    def finalize(self) -> List[Embed]:
        """ Finalize and return the list of split embeds. """
        self._flush_field_cache()
        if not self.repeat_footer:
            footer = self.template.footer
            self.cur_embed.timestamp = self.template.timestamp
            self.cur_embed.set_footer(text=footer.text, icon_url=footer.icon_url)
        self.cur_embed = None
        embeds = list(self._embeds)
        self._embeds.clear()
        return embeds

    def __len__(self):
        return len(self._embeds)


def get_embed_size(e: Embed):
    size = sum(len(s) for s in (e.title, e.description, e.author.name, e.footer.text)
               if s is not EmptyEmbed)
    size_fields = sum(len(f.name) + len(f.value) for f in e.fields)
    return size + size_fields
