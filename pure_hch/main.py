"""Basic Functional HCH"""

"""
Notes on transparent promises:

Answers should be referenceable before they are computed.

In general, an action can be generated that _would_ unlock
an incomplete promise, but the resulting context should
never be scheduled (or, probably, even created) until the
incomplete promise is filled in. This kind of sucks, though,
since it means that the hypertext graph is no longer really
immutable...?

Wait, no, you just have to make answers point at their
questions. A situation doesn't have access to any of its subquestion's
answers; the questions are only visible via some global dataset.
This dataset gets passed into a _context_ but isn't available to a
_situation_.
"""

# TODO: Context visiting currently doesn't work properly - boundaries
# aren't added to the pointer_map, so we'll crash.

import uuid

from collections import deque
from textwrap import indent

POINTER_FMT = "[{}]"
INDENTATION = "  "

class LazyHypertextStore(object):
    """Very un-thread- and un-exception-safe"""
    def __init__(self):
        # Keys to promised hypertext that has not yet been resolved, with
        # a list of holders of the promise, who would like to know about its
        # resolution.
        self.promises = {}

        # There should only ever be one hypertext object with a given value
        # in this datastore.
        self.resolved_store = {}

        # Content Addressing
        # There _can_ be multiple keys that correspond to a hypertext value.
        # In that case, the _first_ of those keys to be created should be stored
        # inside store_values.
        self.resolved_keys_by_value = {}

    def createPromise(self):
        key = uuid.uuid1()
        self.promises[key] = []
        return key

    def valueExists(self, value):
        return value in self.resolved_keys_by_value

    def resolvePromise(self, key, value):
        if key not in self.promises:
            raise ValueError("Promise {} not pending during attempt to resolve".format(key))

        promise_holders = self.promises[key]
        del self.promises[key]
        if self.valueExists(value):
            # Hooray garbage collection!
            self.store[key] = self.store[self.store_values[value]]
        else:
            self.store[key] = value
            self.store_values[value] = key
        return promise_holders

    def isPromiseResolved(self, key):
        return key in self.store

    def getByAddress(self, key):
        return self.store[key]

    def addressOf(self, value):
        return self.store_values[value]

    def getByValue(self, value):
        return 

    def setDefaultValue(self, value):
        """By analogy with dict.setdefault()"""
        if self.valueExists(value):
            key = datastore.addressOf(value)
        else:
            key = self.createPromise()
            self.resolvePromise(key, value)
        return key



class Hypertext(object):
    def __init__(self, chunks):
        self.chunks = chunks
        referents = set()
        for chunk in self.chunks:
            if not isinstance(chunk, str):
                referents.add(chunk)
        self.referents = list(referents)

    def __str__(self):
        return self.toString(pointer_map=None)

    def toString(self, pointer_map=None):
        """String representing the current hypertext fragment, with pointer placeholders."""
        builder = []
        for chunk in self.chunks:
            if isinstance(chunk, str):
                builder.append(chunk)
            else:
                if pointer_map is not None:
                    pointer_to_display = pointer_map[chunk]
                else:
                    pointer_to_display = chunk
                builder.append(POINTER_FMT.format(pointer_to_display))
        return ''.join(builder)


class Question(Hypertext):
    def __init__(self, datastore, query):
        self.query = query
        self.answer = datastore.


class Situation(Hypertext):
    def __init__(self, datastore, predecessor=None, question=None, scratchpad=None, subquestion=None):
        if [predecessor, question].count(None) != 1:
            raise ValueError(
                "A Situation must have exactly one of [predecessor, question].")
        if [question, scratchpad, subquestion].count(None) != 2:
            raise ValueError(
                "A Situation must have exactly one of [question, scratchpad, subquestion].")

        self.predecessor = predecessor
        self.question = question
        self.scratchpad = scratchpad

        # Note that a subquestion should actually be a (question, answer) pair
        self.subquestion = subquestion

        # REVSIIT: not a huge fan of this
        if self.question is not None:
            self.scratchpad = datastore.setDefaultValue(Hypertext([""]))

        self.referents = [self.getQuestion(), self.getScratchpad()]
        for q, a in self.getSubQuestions():
            self.referents.append(q)
            self.referents.append(a)

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
        subquestions = self.getSubQuestions()
        subquestion_queries, subquestion_replies = zip(*subquestions)
        return [self.getQuestion(), self.getScratchpad(), *subquestion_queries, *subquestion_replies]

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
            subquestion.toString(pointer_map=pointer_map)

            builder.append(indent("{}. {}".format(
                i, subquestion_query, subquestion_answer), INDENTATION))

        return "\n".join(builder)


class Context(object):
    def __init__(self, situation, unlocked_addresses, datastore):
        self.situation = situation
        self.unlocked_addresses = unlocked_addresses
        self.normalized_pointers = self._determineNormalization()

    def _visitHypertext(self, procedure, datastore):
        """Call procedure(element) on each element of the unlocked hypertext graph."""
        frontier = deque(self.situation.getAllRootHypertext())
        explored = set(frontier)
        while not frontier.empty():
            current_element = frontier.popleft()
            for item in current_element.referents:
                if item in self.unlocked_addresses and item not in explored:
                    procedure(item)
                    explored.add(item)
                    frontier.push_back(item)


    def _determineNormalization(self):
        """Pointer display must be unique in a context.

        Here we choose a map from object id to display id."""
        mapping = {}
        def addReferentsToMapping(element):
            for link in element.referents:
                if link not in mapping:
                    mapping[link] = len(mapping) + 1

        self._visitHypertext(addReferentsToMapping)
        return mapping

    def __str__(self):
        # I guess this could be done on __init__... we probably call it a lot.
        builder = []
        builder.append(self.situation.strWithPointerMap(self.normalized_pointers))

        def addToBuilder(element):
            pointer_display = POINTER_FMT.format(self.normalized_pointers[element.address()])
            text_display = element.strWithPointerMap(self.normalized_pointers)
            builder.append(indent("{}: {}".format(pointer_display, text_display), INDENTATION))

        self._visitHypertext(addToBuilder)
        return "\n".join(builder)

    def __hash__(self, other):
        # REVISIT along with __eq__
        return hash(str(self))

    def __eq__(self, other):
        # REVISIT - inefficient (though I think this is close to the semantics we want)
        return str(self) == str(other)


class ContextScheduler(object):
    """Not thread- or exception-safe"""
    def __init__(self, datastore=None):
        self.pending_contexts = deque() # contexts that _could_ be worked on but are not
        self.active_contexts = set() # contexts that are currently being worked on
        self.memoized_contexts = {}
        if datastore is None:
            self.datastore = LazyHypertextStore()
        else:
            self.datastore = datastore

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

