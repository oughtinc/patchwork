"""Basic Functional HCH"""

import uuid

from collections import deque
from textwrap import indent

POINTER_FMT = "[{}]"
INDENTATION = "  "

def format_chunk(chunk, display_map):
    # raises KeyError if display_map is not None but also does not contain an element
    # for a pointer-valued chunk
    if isinstance(chunk, str):
        return chunk
    elif display_map is None:
        return POINTER_FMT.format(chunk)
    else:
        return POINTER_FMT.format(display_map[chunk])


class Hypertext(object):
    def __init__(self):
        raise NotImplementedError("Hypertext is pure virtual")

    def __str__(self):
        return self.to_str()

    # REVISIT hash and eq; there are almost certainly better ways.
    def __eq__(self, other):
        return str(self) == str(other)

    def __hash__(self):
        return hash(str(self))

    def links(self):
        # NOTE: Link ordering _MUST NOT_ be dependent on any facts
        # about the links themselves - it can only depend on
        # relative facts about how they relate to the hypertext
        # (e.g. should not rely on their hashes, or what data they
        # point to). This is to ensure that observationally identical
        # contexts have consistent mappings from a pointer id to a
        # relative location in the local graph
        raise NotImplementedError("Hypertext needs to specify links()")

    def to_str(self, pointer_display_map=None):
        raise NotImplementedError("Hypertext needs to implement __str__")


class RawHypertext(Hypertext):
    def __init__(self, chunks):
        self.chunks = chunks

    def links(self):
        result = []
        seen = set()
        for c in self.chunks:
            if isinstance(c, str):
                continue
            if c not in seen:
                result.append(c)
            seen.add(c)
        return result

    def to_str(self, pointer_display_map=None):
        acc = []
        for chunk in self.chunks:
            acc.append(format_chunk(chunk, pointer_display_map))
        return ''.join(acc)


class Question(RawHypertext):
    def __init__(self, chunks, answer_link):
        self.answer_link = answer_link
        self.chunks = chunks

    def links(self):
        return [self.answer_link] + super().links()

    def to_str(self, pointer_display_map=None):
        return "{} : {}".format(
            super().to_str(pointer_display_map=pointer_display_map),
            format_chunk(self.answer_link, pointer_display_map))


class Situation(Hypertext):
    def __init__(self,
                 predecessor=None,
                 question_link=None,
                 scratchpad_link=None,
                 subquestion_link=None):
        # Predecessor should actually be a predecessor object, but the rest are links.

        # Annoyingly complicated rules:
        if question_link is not None:
            # If it has a question, it must have a scratchpad and no subquestion or predecessor.
            assert predecessor is None
            assert subquestion_link is None
            assert scratchpad_link is not None
        else:
            # If it has no question, it must have a predecessor and either a scratchpad
            # xor a subquestion.
            assert predecessor is not None
            assert [scratchpad_link, subquestion_link].count(None) == 1

        self.predecessor = predecessor
        self.question = question_link
        self.scratchpad = scratchpad_link
        self.subquestion = subquestion_link

    def _fold_over_predecessors(self, operation, acc):
        situation = self
        while situation is not None:
            acc = operation(situation, acc)
            situation = situation.predecessor
        return acc

    def get_question(self):
        return self._fold_over_predecessors(lambda s, a: s.question, None)

    def get_scratchpad(self):
        return self._fold_over_predecessors(lambda s, a: a or s.scratchpad, None)

    def get_subquestions(self):
        return self._fold_over_predecessors(
            lambda s, a: ([s.subquestion] if s.subquestion else []) + a, [])

    def links(self):
        return [self.get_question(), self.get_scratchpad(), *self.get_subquestions()]

    def to_str(self, pointer_display_map=None):
        acc = []
        acc.append("Question: {}".format(
            format_chunk(self.get_question(), pointer_display_map)))
        acc.append("Scratchpad: {}".format(
            format_chunk(self.get_scratchpad(), pointer_display_map)))
        acc.append("Subquestions:")
        for subquestion in self.get_subquestions():
            acc.append(indent(
                format_chunk(subquestion, pointer_display_map), INDENTATION))
        return '\n'.join(acc)


class Context(Hypertext):
    def __init__(self, situation, unlocked_locations, datastore):
        self.template_situation = situation
        self.template_unlocked_locations
        self.template_link_display_map = self._build_link_display_map(
            situation, unlocked_locations, datastore)

        self.display = self._build_display(datastore)

    def _map_over_unlocked_region(self, f, root, unlocked_locations, datastore):
        frontier = deque(root.links())
        seen = set(frontier)
        while not frontier.empty():
            link = frontier.popleft()
            if link in unlocked_locations:
                content = datastore.dereference(link)
                f(link, content)
                for nextlink in content.links():
                    if nextlink not in seen:
                        frontier.pushright(nextlink)
                        seen.add(nextlink)

    def _build_link_display_map(self, root, unlocked_locations, datastore):
        result = {}

        def assign_pointer_view(_, content):
            for link in content.links():
                if link not in result:
                    result[link] = len(result) + 1

        self._map_over_unlocked_region(assign_pointer_view,
                                       root,
                                       unlocked_locations,
                                       datastore)
        return result

    def _build_display(self, datastore):
        acc = []
        acc.append("Question:")
        acc.append(
            textwrap.indent(
                datastore.dereference(
                    self.template_situation.get_question()
                ).to_str(pointer_display_map=self.template_link_display_map),
                INDENTATION
            )
        )

        acc.append("Scratchpad:")
        acc.append(
            textwrap.indent(
                datastore.dereference(
                    self.template_situation.get_scratchpad()
                ).to_str(pointer_display_map=self.template_link_display_map),
                INDENTATION
            )
        )

        acc.append("Subquestions:")
        for i, subquestion in enumerate(self.template_situation.get_subquestions(), start=1):
            acc.append(
                textwrap.indent(
                    "{}. {}".format(
                        i,
                        datastore.dereference(subquestion).to_str(
                            pointer_display_map=self.template_link_display_map
                        )
                    ),
                    INDENTATION
                )
            )

        # okay, since the values in the display map are unique integers
        inverted_display_map = list(
            sorted((v, k) for (k, v) in self.template_link_display_map.items()))

        acc.append("Unlocked Data:")
        for display_number, link in inverted_display_map:
            if link in self.unlocked_locations:
                acc.append(
                    textwrap.indent(
                        "{}. {}".format(
                            display_number,
                            datastore.dereference(link).to_str(
                                pointer_display_map=self.template_link_display_map)
                        ),
                        INDENTATION
                    )
                )
        return "\n".join(acc)


    def links(self):
        # A Context has no links, only variables
        return []

    def to_str(self, pointer_display_map=None):
        return self.display


class Datastore(object):
    def __init__(self):
        self.data = {}
        self.unfulfilled_promises = {}
        self.EMPTY = self.insert(RawHypertext([""]))

    def dereference(self, link):
        return self.data[link]

    def make_promise(self):
        link = uuid.uuid1()
        self.unfulfilled_promises[link] = []
        return link

    def register_promisee(self, link, promisee):
        self.unfulfilled_promises[link].append(promisee)

    def fulfill_promise(self, link, value):
        promisees = self.unfulfilled_promises[link]
        del self.unfulfilled_promises[link]
        self.data[link] = value
        return promisees

    def insert(self, value):
        key = self.make_promise()
        self.fulfill_promise(key, value)
        return key


class Action(object):
    def __init__(self, context):
        raise NotImplementedError("Action is a pure abstract class.")

    def execute(self, datastore, situation):
        raise NotImplementedError("Action subclasses must implement execute")


class EditScratchpad(Action):
    def __init__(self, context, edit_contents):
        self.context = context
        self.edit_contents = edit_contents


class AskSubQuestion(Action):
    def __init__(self, context, question_contents):
        self.context = context
        self.question_contents = question_contents


class AnswerQuestion(Action):
    def __init__(self, context, question_index, answer_contents):
        self.context = context
        self.question_index = question_index
        self.answer_contents = answer_contents


class ExportScratchpad(Action):
    def __init__(self, context):
        self.context = context


class UnlockPointer(Action):
    def __init__(self, context, pointer_index):
        self.context = context
        self.pointer_index = pointer_index


