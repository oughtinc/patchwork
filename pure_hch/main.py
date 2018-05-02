"""Basic Functional HCH"""

# TODO: The current system is pretty weak.
# pointers are assumed to actually point at something. :(
# The easiest way to solve this seems likely to be to wrap
# all hypertext references inside some form of promise.

import uuid

from collections import deque
from textwrap import indent

POINTER_FMT = "[{}]"
INDENTATION = "  "

class Hypertext(object):
    def __init__(self, chunks, referents):
        self.chunks = chunks
        self.referents = referents
        self.uuid = uuid.uuid1()

    def __str__(self):
        return self.toString(pointer_map=None, depth=0)

    def address(self):
        # This could almost just be id(self), but that would break if we persist data.
        # There are probably much better ways to do this - a global counter might be
        # good enough; if this were stored in a database it could be (table, pk).
        return self.uuid

    def toString(self, pointer_map=None):
        builder = []
        for chunk in self.chunks:
            if isinstance(chunk, str):
                builder.append(chunk)
            else:
                if pointer_map is not None:
                    pointer_display = pointer_map[self.referents[chunk].address()]
                else:
                    pointer_display = chunk
                builder.append(POINTER_FMT.format(pointer_display))
        return ''.join(builder)


class Situation(Hypertext):
    def __init__(self, predecessor=None, question=None, scratchpad=None, subquestion=None):
        if [predecessor, question].count(None) != 1:
            raise ValueError(
                "A Situation must have exactly one of "
                "[predecessor, question].")
        if [question, scratchpad, subquestion].count(None) != 2:
            raise ValueError(
                "A Situation must have exactly one of "
                "[question, scratchpad, subquestion].")

        self.predecessor = predecessor
        self.question = question
        self.scratchpad = scratchpad
        self.subquestion = subquestion

        if self.question is not None:
            self.scratchpad = Hypertext([""], [])

        self.referents = [self.getQuestion(), self.getScratchpad(), *self.getSubQuestions()]

    def _getMostRecentFieldFromAncestors(self, accessor):
        # naturally tail recursive but python doesn't know that
        situation = self
        while situation is not None:
            field = accessor(situation)
            if field is not None:
                return field
            else:
                situation = situation.predecessor
        raise ValueError("Could not find a predecessor with the given field.")

    def _accumulateFieldFromAncestors(self, accessor):
        acc_reverse = []
        situation = self
        while situation is not None:
            field = accessor(situation)
            if field is not None:
                acc_reverse.append(field)
            situation = situation.predecessor
        return reversed(acc_reverse)

    def getQuestion(self):
        return self._getMostRecentFieldFromAncestors(lambda s: s.question)

    def getScratchpad(self):
        return self._getMostRecentFieldFromAncestors(lambda s: s.scratchpad)

    def getSubQuestions(self):
        return self._accumulateFieldFromAncestors(lambda s: s.subquestion)

    def getSubQuestionsStr(self):
        return "\n".join(str(q) for q in self.getSubQuestions())

    def getAllRootHypertext(self):
        return [self.getQuestion(), self.getScratchpad(), *self.getSubQuestions()]

    def toString(self, pointer_map=None):
        builder = []
        builder.append("Question:")
        builder.append(
            indent(self.getQuestion().toString(pointer_map=pointer_map), INDENTATION))

        builder.append("Scratchpad:")
        builder.append(
            indent(self.getScratchpad().toString(pointer_map=pointer_map), INDENTATION))

        builder.append("Subquestions:")
        for i, subquestion in enumerate(self.getSubquestions(), start=1):
            builder.append(indent("{}. {}".format(
                i, subquestion.toString(pointer_map=pointer_map)), INDENTATION))

        return "\n".join(builder)


class Context(object):
    def __init__(self, situation, unlocked_addresses):
        self.situation = situation
        self.unlocked_addresses = unlocked_addresses
        self.normalized_pointers = self._determineNormalization()

    def _visitHypertext(self, procedure):
        """Call procedure(element, count) on each element of the unlocked hypertext graph."""
        pointer_count = 0
        frontier = deque(self.situation.getAllRootHypertext())
        explored = set(frontier)
        while not frontier.empty():
            current_element = frontier.popleft()
            for item in current_element.referents:
                if item in self.unlocked_addresses and item not in explored:
                    pointer_count += 1
                    procedure(item, pointer_count)
                    explored.add(item)
                    frontier.push_back(item)
        return pointer_count


    def _determineNormalization(self):
        """Pointer display must be unique in a context.

        Here we choose a map from object id to display id."""
        mapping = {}
        def addToMapping(element, element_index):
            mapping[element.address()] = element_index

        self._visitHypertext(addToMapping)
        return mapping

    def __str__(self):
        # I guess this could be done on __init__... we probably call it a lot.
        builder = []
        builder.append(self.situation.strWithPointerMap(self.normalized_pointers))

        def addToBuilder(element, element_index):
            pointer_display = POINTER_FMT.format(self.normalized_pointers[element.address()])
            text_display = element.strWithPointerMap(self.normalized_pointers)
            builder.append(indent("{}: {}".format(pointer_display, text_display), INDENTATION))

        self._visitHypertext(addToBuilder)
        return "\n".join(builder)

    def __hash__(self, other):
        # REVISIT along with __eq__
        return hash(str(self))

    def __eq__(self, other):
        # REVISIT - inefficient
        return str(self) == str(other)


class ContextScheduler(object):
    # TODO: Not thread- or exception-safe
    def __init__(self):
        self.pending_contexts = deque() # contexts that _could_ be worked on but are not
        self.active_contexts = set() # contexts that are currently being worked on

    def chooseContext(self):
        if self.pending_contexts.empty():
            return None
        else:
            result = pending_contexts.popleft()
            self.active_contexts.add(result)
            return result

    def abortContext(self, context):
        self.pending_contexts.pushleft(context)
        self.active_contexts.delete(context)

    def completeContext(self, context, action):
        self.active_contexts.remove(context)

