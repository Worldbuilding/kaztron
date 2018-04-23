from collections import abc
from datetime import datetime
from typing import Sequence, Mapping, Dict, Callable, Any, Optional, Union

from kaztron.utils.datetime import utctimestamp


Validator = Callable[[str], Any]
QuestionGetter = Callable[[], str]


def make_wizard(
                 keys: Sequence[str],
                 questions: Mapping[str, Union[str, QuestionGetter]],
                 validators: Mapping[str, Optional[Validator]],
                 optional_keys: Sequence[str]=tuple()):
    """
    Create a simple (linear) wizard, asking questions to the user in sequence. This simple wizard
    does not allow for conditional or branching question paths.

    This method returns a Mapping-derived class that can then be instantiated for each time a user
    needs to be questioned. The collected data can be used by treating the instance object as a
    mapping/dict, e.g., passing it as a kwargs dict using the ``**`` operator.

    :param keys: A list of keyword arguments, in the order they should be asked for.
    :param questions: Mapping of keys to question text to show the user. Text also be a callable
        for dynamic question text.
    :param validators: Mapping of keys to validators/converter callables. These callables should
        either return the final/converted value, or raise any exception.
    :param optional_keys: A list of keyword arguments that can be None/skipped by the user.
        All fields must appear in the ``fields`` list as well.
    :return: Wizard class
    """

    if not keys:
        raise ValueError("No keys passed")

    for f in optional_keys:
        if f not in keys:
            raise ValueError("Optional field {!r} is not in fields list".format(f))

    for f in keys:
        if f not in questions:
            raise ValueError("Missing question for field {!r}".format(f))

    class Wizard(abc.Mapping):
        """
        Mapping that can be used for a simple (linear) wizard, asking questions to the user in
        sequence.

        :param user_id: Discord ID of the member this wizard is running for.
        :param timestamp: The time this wizard was started at.
        """
        NONE_VALUES = ('none', 'n/a', 'null')
        keys = list(keys)
        opts = list(optional_keys)
        questions = dict(questions)
        validators = dict(validators)

        @classmethod
        def from_dict(cls, wizard_dict: dict) -> 'Wizard':
            o = cls(wizard_dict['user_id'], datetime.utcfromtimestamp(wizard_dict['timestamp']))
            data = wizard_dict['data']  # type: Dict[str, str]
            try:
                for key in cls.keys:
                    o.answer(data[key])
            except (IndexError, StopIteration):
                pass
            return o

        def __init__(self, user_id: str, timestamp: datetime=None):
            self.user_id = user_id
            self.timestamp = timestamp if timestamp else datetime.utcnow()
            self.data = {}
            self._current = 0

        def to_dict(self):
            return {
                'user_id': self.user_id,
                'timestamp': utctimestamp(self.timestamp),
                'data': self.data.copy()
            }

        @property
        def current_key(self) -> str:
            """ The current key, or raise IndexError if no more questions. """
            return self.keys[self._current]

        @property
        def question(self) -> str:
            """ The next question, or raise IndexError if no more questions."""
            q = self.questions[self.current_key]
            if isinstance(q, str):
                return q
            else:
                return q()

        def answer(self, value):
            """ Input the next value. If this is the last possible value, raise StopIteration. """
            validate = self.validators.get(self.current_key, None)
            if validate:
                try:
                    value = validate(value)
                except Exception as e:
                    raise ValueError("Invalid answer: " + e.args[0]) from e

            if self.current_key in self.opts:
                if value.lower() in self.NONE_VALUES:
                    value = None
            elif value is None:
                raise ValueError("Invalid answer: validator returned None")

            self.data[self.current_key] = value

            # update state for next question
            self._current += 1
            if self._current >= len(self.keys):
                raise StopIteration

        def __iter__(self):
            return iter(self.data)

        def __len__(self):
            return len(self.data)

        def __getitem__(self, key):
            return self.data[key]

    return Wizard

def len_validator(maxlen: int) -> Validator:
    def validate(s: str):
        if len(s) > maxlen:
            raise ValueError("Answer too long ({:d})".format(len(s)))
        return s
    return validate
