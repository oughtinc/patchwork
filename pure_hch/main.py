"""Basic Functional HCH"""

import cmd
import logging
import os
import pickle
import sys
import uuid

from collections import defaultdict, deque
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
    # We are kind of abusing python's idea of "equality", especially
    # when the scheduler is using Contexts as keys in various containers
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

    def subquestion_link_by_index(self, index):
        return self.get_subquestions()[index]

    def links(self):

        return [self.get_question(), self.get_scratchpad()] + self.get_subquestions()

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
    def __init__(self, situation_link, unlocked_locations, datastore):
        self.template_situation_link = situation_link
        self.template_unlocked_locations = unlocked_locations
        self.template_link_display_map = self._build_link_display_map(
            datastore.dereference(situation_link), datastore)

        self.display = self._build_display(datastore)

    def _map_over_unlocked_region(self, f, root, datastore):
        # TODO: I'm not sure exactly what properties this search requires of
        # the two directed graphs it's searching over. It will certainly work
        # if they have the exact same structure, down to address equality, but
        # it might not work if they merely have observationally identical structure.
        # That is, if the two graphs would stringify to the same thing, but have different
        # underlying structures.

        # An example might be if self.template_situation has a structure that looks
        # like A->B->C, D->B->C, while root has a structure a->b->c, d->e->c (where b
        # and d have observationally identical content but different addresses).

        # I _THINK_ that this can't happen in practice, since these graphs actually
        # wouldn't be observationally identical.

        # NOTE: This is why link orderings _must_ be stable and not change when
        # the hypertext object is observationally identical.
        template_situation = datastore.dereference(self.template_situation_link)
        assert(len(template_situation.links()) == len(root.links()))
        frontier = deque(zip(template_situation.links(), root.links()))
        seen = set(frontier)
        while len(frontier) > 0:
            template_link, mirror_link = frontier.popleft()
            if template_link in self.template_unlocked_locations:
                template_content = datastore.dereference(template_link)
                mirror_content = datastore.dereference(mirror_link)
                f(mirror_link, mirror_content)
                assert(len(template_content.links()) == len(mirror_content.links()))
                for next_links in zip(template_content.links(), mirror_content.links()):
                    if next_links not in seen:
                        frontier.append(next_links)
                        seen.add(next_links)

    def _build_link_display_map(self, root, datastore):
        result = {}

        def assign_pointer_view(_, content):
            for link in content.links():
                if link not in result:
                    result[link] = len(result) + 1

        self._map_over_unlocked_region(assign_pointer_view,
                                       root,
                                       datastore)
        return result

    def _invert_display_map(self, display_map):
        # okay, since the values in the display map are unique integers
        return list(sorted((v, k) for (k, v) in display_map.items()))


    def _build_display(self, datastore):
        template_situation = datastore.dereference(self.template_situation_link)

        def deref_and_indent(link):
            # Indentation here is used to enforce that the relevant parts of the
            # logical structure of a context are unambiguous: Any sub-elements
            # of the context are indented, while any structural delimiters are not.
            return indent(
                datastore.dereference(link).to_str(
                    pointer_display_map=self.template_link_display_map
                ),
                INDENTATION
            )

        acc = []
        acc.append("Question:")
        acc.append(deref_and_indent(template_situation.get_question()))

        acc.append("Scratchpad:")
        acc.append(deref_and_indent(template_situation.get_scratchpad()))

        acc.append("Subquestions:")
        for i, subquestion in enumerate(template_situation.get_subquestions(), start=1):
            acc.append("{}.{}".format(i, deref_and_indent(subquestion)))

        acc.append("Unlocked Data:")
        logging.warn(self.template_unlocked_locations)
        for display_number, link in self._invert_display_map(self.template_link_display_map):
            logging.warn(link)
            if link in self.template_unlocked_locations:
                acc.append("{}.{}".format(display_number, deref_and_indent(link)))
        return "\n".join(acc)

    def links(self):
        # A Context has no links - it _is_ what the user sees, and is not situated in the
        # hypertext web, except potentially as an object that can be pointed at.
        return []

    def to_str(self, pointer_display_map=None):
        return self.display

    def renormalize_pointer(self, situation, index, datastore):
        for link, key in self._build_link_display_map(situation, datastore).items():
            if key == index:
                return link
        raise ValueError("Index not found in context")

    def renormalize_hypertext(self, situation, hypertext_chunks, datastore):
        result = []
        pointer_map = dict(
            self._invert_display_map(self._build_link_display_map(situation, datastore)))
        for chunk in hypertext_chunks:
            if isinstance(chunk, str):
                result.append(chunk)
            else:
                result.push_back(pointer_map[chunk])
        return result

    def map_unlocked_locations(self, situation, datastore):
        result = []
        self._map_over_unlocked_region(lambda l, c: result.append(l), situation, datastore)
        return result


class Datastore(object):
    # REVISIT: It might be nice to have the datastore deduplicate
    # identical content; this would plausibly help with some cycle
    # checking
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

    def is_fulfilled(self, link):
        if link in self.data:
            return True

    def insert(self, value):
        key = self.make_promise()
        self.fulfill_promise(key, value)
        return key


class Action(object):
    # REVISIT: Should Action inherit from Hypertext? Seems like maybe?

    # REVISIT: insert contexts into datstores as they're created? right
    # now there won't be much affordance for doing anything useful with them
    def __init__(self, context):
        raise NotImplementedError("Action is a pure abstract class.")

    def execute(self, datastore, situation_link):
        raise NotImplementedError("Action subclasses must implement execute")


class EditScratchpad(Action):
    # TODO: Scratchpad edits can result in annoying infinite loops;
    # I'm not sure exactly how to deal with this.

    # Budgets would probably save me

    # Could also add some kind of infinite loop checking
    def __init__(self, context, edit_contents):
        self.context = context
        self.edit_contents = edit_contents


class ExportScratchpad(Action):
    def __init__(self, context):
        self.context = context


class AskSubQuestion(Action):
    def __init__(self, context, question_contents):
        self.context = context
        self.question_contents = question_contents

    def execute(self, datastore, situation_link):
        situation = datastore.dereference(situation_link)

        # 1. Get a version of the question contents that are
        # relevant to the passed in situation
        concrete_contents = self.context.renormalize_hypertext(
            situation, self.question_contents, datastore)

        # 2. Create and insert a subquestion from those contents
        answer_link = datastore.make_promise()
        new_question_link = datastore.insert(Question(concrete_contents, answer_link))

        # 3. Create and insert a situation based on the passed in situation
        # and the question we've created
        successor_situation = Situation(predecessor=situation, subquestion_link=new_question_link)
        successor_situation_link = datastore.insert(successor_situation)
        mapped_unlocked_locations = self.context.map_unlocked_locations(situation, datastore)
        mapped_unlocked_locations.append(new_question_link)

        # 4. Also create and insert a situation for the subquestion.
        subquestion_situation = Situation(
            question_link=new_question_link, scratchpad_link=datastore.EMPTY)
        subquestion_situation_link = datastore.insert(subquestion_situation)

        # 5. yield a context for each of the created situations.
        yield Context(subquestion_situation_link, subquestion_situation.links(), datastore)
        yield Context(successor_situation_link, mapped_unlocked_locations, datastore)


class AnswerQuestion(Action):
    def __init__(self, context, answer_contents):
        self.context = context
        self.answer_contents = answer_contents

    def execute(self, datastore, situation_link):
        situation = datastore.dereference(situation_link)

        # 1. Figure out the answer link
        question_link = situation.get_question()
        answer_link = datastore.dereference(question_link).answer_link

        # 2. Get a version of the answer contents that are relevant to the passed in situation
        concrete_contents = self.context.renormalize_hypertext(situation, self.answer_contents, datastore)

        # 3. Create an answer with the contents
        answer = RawHypertext(concrete_contents)

        # 4. Fulfill the promise relevant to the question and yield each of the promisees
        for situation_link, mapped_unlocked_locations in datastore.fulfill_promise(answer_link, answer):
            yield Context(situation_link, mapped_unlocked_locations, datastore)


class UnlockPointer(Action):
    def __init__(self, context, pointer_display_index):
        self.context = context
        self.pointer_display_index = pointer_display_index

    def execute(self, datastore, situation_link):
        situation = datastore.dereference(situation_link)

        # 1. Figure out which link the pointer index corresponds to
        pointer_link = self.context.renormalize_pointer(
            situation, self.pointer_display_index, datastore)

        # 2. Create a context that points to this situation and is identical
        # to the initial context, but with the link in its set of unlocked pointers
        mapped_unlocked_locations = self.context.map_unlocked_locations(situation, datastore)
        mapped_unlocked_locations.append(pointer_link)

        if datastore.is_fulfilled(pointer_link):
            # 3. If the pointer is fulfilled, yield the context.
            yield Context(situation_link, mapped_unlocked_locations, datastore)
        else:
            # 4. If not, add the context to the pointer's promisees
            datastore.register_promisee(pointer_link, (situation_link, mapped_unlocked_locations))


class Scheduler(object):
    def __init__(self, datastore):
        self.datastore = datastore
        self.pending_contexts = deque()
        self.cached_actions = {}

    def schedule_context(self, context):
        self.pending_contexts.append(context)

    def choose_context(self):
        while self.pending_contexts[0] in self.cached_actions:
            cached_context = self.pending_contexts.popleft()
            cached_action = self.cached_actions[cached_context]
            resulting_contexts = cached_action.execute(self.datastore, cached_context.template_situation_link)
            self.pending_contexts.extend(resulting_contexts)
        return self.pending_contexts.popleft()

    def resolve_action(self, context, action):
        self.cached_actions[context] = action
        self.pending_contexts.extend(action.execute(self.datastore, context.template_situation_link))


def parse_chunks(arg):
    result = []
    # HACK
    while True:
        try:
            start, rest = arg.split("[", 1)
            pointer, arg = arg.split("]", 1)
            result.append(start, int(pointer))
        except ValueError:
            result.append(arg)
            break
    return result


class UserInterface(cmd.Cmd):
    intro = "What is your root question?"
    prompt = "> "
    def __init__(self, datastore, scheduler):
        super().__init__()
        self.datastore = datastore
        self.scheduler = scheduler
        self.current_workspace = None

    def default(self, line):
        if self.current_workspace is None:
            answer_link = self.datastore.make_promise()
            question_link = self.datastore.insert(Question([line], answer_link))
            situation = Situation(scratchpad_link=self.datastore.EMPTY, question_link=question_link)
            situation_link = self.datastore.insert(situation)
            new_context = Context(situation_link, situation.links(), self.datastore)
            self.scheduler.schedule_context(new_context)
            self.current_workspace = self.scheduler.choose_context()
        else:
            return super().default(line)

    def precmd(self, line):
        print("---")

        return line

    def postloop(self):
        if self.current_workspace is None:
            return
        else:
            print(self.current_workpace)

    def postcmd(self, stop, line):
        self.prompt = str(self.current_workspace) + "\n" + UserInterface.prompt
        return stop

    def emptyline(self):
        pass

    def do_ask(self, arg):
        """Ask a subquestion"""
        action = AskSubQuestion(self.current_workspace, parse_chunks(arg))
        self.scheduler.resolve_action(self.current_workspace, action)
        self.current_workspace = self.scheduler.choose_context()

    def do_reply(self, arg):
        """Provide an answer to this question."""
        action = AnswerQuestion(self.current_workspace, parse_chunks(arg))
        self.scheduler.resolve_action(self.current_workspace, action)
        self.current_workspace = self.scheduler.choose_context()

    def do_unlock(self, arg):
        """Unlock a pointer"""
        action = UnlockPointer(self.current_workspace, int(arg))
        self.scheduler.resolve_action(self.current_workspace, action)
        self.current_workspace = self.scheduler.choose_context()


def main(argv):
    datastore = Datastore()
    scheduler = Scheduler(datastore)
    interface = UserInterface(datastore, scheduler)
    interface.cmdloop()

if __name__ == "__main__":
    main(sys.argv)

