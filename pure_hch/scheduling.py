import logging

from collections import defaultdict, deque
from textwrap import indent
from typing import Callable, DefaultDict, Deque, Dict, Generator, List, Optional, Set, Tuple

from .datastore import Address, Datastore
from .hypertext import Workspace

from .text_manipulation import create_raw_hypertext, insert_raw_hypertext


class Context(object):
    def __init__(
            self,
            workspace_link: Address,
            db: Datastore,
            unlocked_locations: Optional[Set[Address]]=None,
            ) -> None:

        # Unlocked locations should be in terms of the passed in workspace_link.

        self.workspace_link = workspace_link
        workspace = db.dereference(workspace_link)
        if unlocked_locations is not None:
            self.unlocked_locations = unlocked_locations
            self.unlocked_locations.add(self.workspace_link)
        else:
            # All of the things that are visible in a context with no explicit unlocks.
            self.unlocked_locations = set(
                    [workspace_link, workspace.question_link, workspace.scratchpad_link] +
                    [q for q, a, w in workspace.subquestions] +
                    ([workspace.predecessor_link] if workspace.predecessor_link else []))

        self.pointer_names, self.name_pointers = self._name_pointers(self.workspace_link, db)
        self.display = self.to_str(db)

    def _map_over_unlocked_workspace(
            self,
            workspace_link: Address,
            db: Datastore,
            ) -> Generator[Address, None, None]:
        frontier = deque([(self.workspace_link, workspace_link)])
        seen = set(frontier)
        while len(frontier) > 0:
            my_link, your_link = frontier.popleft()
            if my_link in self.unlocked_locations:
                yield your_link
                my_page = db.dereference(my_link)
                your_page = db.dereference(your_link)
                for next_links in zip(my_page.links(), your_page.links()):
                    if next_links not in seen:
                        frontier.append(next_links)
                        seen.add(next_links)

    def _name_pointers(
            self,
            workspace_link: Address,
            db: Datastore,
            ) -> Tuple[Dict[Address, str], Dict[str, Address]]:
        pointers: Dict[Address, str] = {}
        backward_pointers: Dict[str, Address] = {}

        def assign(link, string):
            pointers[link] = string
            backward_pointers[string] = link

        workspace_root = db.dereference(workspace_link)
        for i, subquestion in reversed(list(enumerate(workspace_root.subquestions, start=1))):
            # Pyre doesn't like tuple destructuring in loops apparently.
            q, a, w = subquestion
            assign(q, "$q{}".format(i))
            assign(a, "$a{}".format(i))
            assign(w, "$w{}".format(i))

        count = 0
        for your_link in self._map_over_unlocked_workspace(workspace_link, db):
            your_page = db.dereference(your_link)
            for visible_link in your_page.links():
                if visible_link not in pointers:
                    count += 1
                    assign(visible_link, "${}".format(count))

        return pointers, backward_pointers


    def unlocked_locations_from_workspace(
            self,
            workspace_link: Address,
            db: Datastore,
            ) -> Set[Address]:
        result = set(self._map_over_unlocked_workspace(workspace_link, db))
        return result

    def name_pointers_for_workspace(
            self,
            workspace_link: Address,
            db: Datastore
            ) -> Dict[str, Address]:
        return self._name_pointers(workspace_link, db)[1]


    def to_str(self, db: Datastore) -> str:
        INLINE_FMT = "[{pointer_name}: {content}]"
        CONTEXT_FMT = "{predecessor}Question: {question}\nScratchpad: {scratchpad}\nSubquestions:\n{subquestions}\n"

        # We need to construct this string in topological order since pointers
        # are substrings of other unlocked pointers. Since everything is immutable
        # once created, we are guaranteed to have a DAG.
        include_counts: DefaultDict[Address, int] = defaultdict(int)

        for link in self._map_over_unlocked_workspace(self.workspace_link, db):
            page = db.dereference(link)
            for visible_link in page.links():
                include_counts[visible_link] += 1

        assert(include_counts[self.workspace_link] == 0)
        no_incomings = deque([self.workspace_link])
        order: List[Address] = []
        while len(no_incomings) > 0:
            link = no_incomings.popleft()
            order.append(link)
            if link in self.unlocked_locations:
                page = db.dereference(link)
                for outgoing_link in page.links():
                    include_counts[outgoing_link] -= 1
                    if include_counts[outgoing_link] == 0:
                        no_incomings.append(outgoing_link)

        link_texts: Dict[Address, str] = {}

        for link in reversed(order):
            if link == self.workspace_link:
                continue
            if link not in self.unlocked_locations:
                link_texts[link] = self.pointer_names[link]
            else:
                page = db.dereference(link)
                link_texts[link] = INLINE_FMT.format(
                        pointer_name=self.pointer_names[link],
                        content=page.to_str(display_map=link_texts))

        subquestion_builder = []
        workspace: Workspace = db.dereference(self.workspace_link)
        for i, subquestion in enumerate(workspace.subquestions, start=1):
            q, a, w = subquestion
            q_text = link_texts[q]
            a_text = link_texts[a]
            w_text = link_texts[w]
            subquestion_builder.append("{}.\n{}\n{}\n{}".format(i, indent(q_text, "  "), indent(a_text, "  "), indent(w_text, "  ")))
        subquestions = "\n".join(subquestion_builder)

        if workspace.predecessor_link is None:
            predecessor = ""
        else:
            predecessor = "Predecessor: {}\n".format(link_texts[workspace.predecessor_link])

        return CONTEXT_FMT.format(
                predecessor=predecessor,
                question=link_texts[workspace.question_link],
                scratchpad=link_texts[workspace.scratchpad_link],
                subquestions=subquestions)


    def __str__(self) -> str:
        return self.display

    def __hash__(self) -> int:
        return hash(str(self))

    def __eq__(self, other: object) -> bool:
        if type(other) is not Context:
            return False
        return str(other) == str(self)



class Action(object):
    def execute(
            self,
            db: Datastore,
            context: Context,
            current_workspace_link: Address,
            ) -> Tuple[Optional[Context], List[Context]]:
        # Successor context should be first if action is deterministic;
        # otherwise it should be last.
        raise NotImplementedError("Action is pure virtual")

    def branches_contexts(self):
        raise NotImplementedError("Action is pure virtual")


class AskSubquestion(Action):
    def __init__(self, question_text: str) -> None:
        self.question_text = question_text

    def branches_contexts(self):
        return False

    def would_introduce_cycle(self, db: Datastore, sub_workspace: Workspace) -> bool:
        workspace_link: Optional[Address] = sub_workspace.parent_link
        while workspace_link is not None:
            workspace = db.dereference(workspace_link)
            if workspace.question_link == sub_workspace.question_link:
                return True
            workspace_link = workspace.parent_link
        return False

    def execute(
            self,
            db: Datastore,
            context: Context,
            current_workspace_link: Address,
            ) -> Tuple[Optional[Context], List[Context]]:

        subquestion_link = insert_raw_hypertext(
                self.question_text,
                db,
                context.name_pointers_for_workspace(current_workspace_link, db))

        answer_link = db.make_promise()
        final_sub_workspace_link = db.make_promise()

        scratchpad_link = insert_raw_hypertext("", db, {})
        sub_workspace = Workspace(
                subquestion_link,
                answer_link,
                final_sub_workspace_link,
                scratchpad_link,
                [],
                current_workspace_link)
        current_workspace = db.dereference(current_workspace_link)

        if self.would_introduce_cycle(db, sub_workspace):
            # REVISIT: In unusually bad cases this might put the scheduler into a weird state. I'm not
            # sure whether that's possible or not.
            raise ValueError("Taking this action would introduce a cycle into the dependency graph")

        sub_workspace_link = db.insert(sub_workspace)
        sub_workspace = db.dereference(sub_workspace_link) # in case our copy was actually clobbered.

        new_subquestions = (current_workspace.subquestions +
                [(subquestion_link, sub_workspace.answer_promise, sub_workspace.final_workspace_promise)])
        successor_workspace = Workspace(
                current_workspace.question_link,
                current_workspace.answer_promise,
                current_workspace.final_workspace_promise,
                current_workspace.scratchpad_link,
                new_subquestions,
                current_workspace.parent_link,
                predecessor_link=current_workspace_link)

        successor_workspace_link = db.insert(successor_workspace)
        successor_workspace = db.dereference(successor_workspace_link)

        new_unlocked_locations = set(context.unlocked_locations_from_workspace(
            current_workspace_link, db))
        new_unlocked_locations.remove(current_workspace_link)
        new_unlocked_locations.add(subquestion_link)
        new_unlocked_locations.add(successor_workspace_link)

        return (
                Context(
                    successor_workspace_link,
                    db,
                    unlocked_locations=new_unlocked_locations),
                [Context(sub_workspace_link, db)])


class Reply(Action):
    def __init__(self, reply_text: str) -> None:
        self.reply_text = reply_text

    def branches_contexts(self):
        return True

    def execute(
            self,
            db: Datastore,
            context: Context,
            current_workspace_link: Address,
            ) -> Tuple[Optional[Context], List[Context]]:

        current_workspace = db.dereference(current_workspace_link)

        reply_hypertext = create_raw_hypertext(
                self.reply_text,
                db,
                context.name_pointers_for_workspace(current_workspace_link, db))

        # final_workspace_promise and answer_promise aren't in
        # workspace.links(), so this is fine (doesn't create
        # link cycles).
        if not db.is_fulfilled(current_workspace.answer_promise):
            answer_successors = db.resolve_promise(current_workspace.answer_promise, reply_hypertext)
        else:
            answer_successors = []

        if not db.is_fulfilled(current_workspace.final_workspace_promise):
            workspace_successors = db.resolve_promise(
                    current_workspace.final_workspace_promise,
                    current_workspace)
        else:
            workspace_successors = []

        all_successors = [Context(args[0], db, args[1])
                for args in answer_successors + workspace_successors]

        return (None, all_successors)


class Unlock(Action):
    def __init__(self, unlock_text: str) -> None:
        self.unlock_text = unlock_text

    def branches_contexts(self):
        return True

    def execute(
            self,
            db: Datastore,
            context: Context,
            current_workspace_link: Address,
            ) -> Tuple[Optional[Context], List[Context]]:

        try:
            pointer_address = context.name_pointers_for_workspace(
                    current_workspace_link,
                    db
                    )[self.unlock_text]
        except KeyError:
            raise ValueError("{} is not visible in this context".format(self.unlock_text))

        new_unlocked_locations = set(context.unlocked_locations_from_workspace(
                current_workspace_link, db))

        if pointer_address in new_unlocked_locations:
            raise ValueError("{} is already unlocked.".format(self.unlock_text))

        new_unlocked_locations.add(pointer_address)

        successor_context_args = (current_workspace_link, new_unlocked_locations)

        if db.is_fulfilled(pointer_address):
            return (None, [Context(successor_context_args[0], db, successor_context_args[1])])

        db.register_promisee(pointer_address, successor_context_args)
        return (None, [])


class Scratch(Action):
    def __init__(self, scratch_text: str) -> None:
        self.scratch_text = scratch_text

    def branches_contexts(self):
        return False

    def execute(
            self,
            db: Datastore,
            context: Context,
            current_workspace_link: Address,
            ) -> Tuple[Optional[Context], List[Context]]:

        new_scratchpad_link = insert_raw_hypertext(
                self.scratch_text,
                db,
                context.name_pointers_for_workspace(current_workspace_link, db))

        current_workspace = db.dereference(current_workspace_link)

        successor_workspace = Workspace(
                current_workspace.question_link,
                current_workspace.answer_promise,
                current_workspace.final_workspace_promise,
                new_scratchpad_link,
                current_workspace.subquestions,
                current_workspace.parent_link,
                predecessor_link=current_workspace_link)

        successor_workspace_link = db.insert(successor_workspace)

        successor_workspace = db.dereference(successor_workspace_link)

        new_unlocked_locations = set(context.unlocked_locations_from_workspace(
                current_workspace_link,
                db))
        new_unlocked_locations.remove(current_workspace_link)
        new_unlocked_locations.add(successor_workspace_link)
        new_unlocked_locations.add(new_scratchpad_link)

        return (
                Context(
                    successor_workspace_link,
                    db,
                    unlocked_locations=new_unlocked_locations),
                []
                )


class Scheduler(object):
    def __init__(self, initial_question: str, db: Datastore) -> None:
        self.db = db
        # The scheduler is, at almost any moment, in the middle
        # of a non-branching sequence of actions.

        # There should always be a current context, a last branching context
        # (which can be the same), and a list of actions that have been taken
        # since the last branching context.
        self.last_branching_context = self.ask_root_question(initial_question)
        self.current_context: Optional[Context] = self.last_branching_context
        self.unbranched_actions: List[Action] = []
        self.cache: Dict[Context, List[Action]] = {}
        self.branches: Deque[Context] = deque()

    def ask_root_question(self, contents: str) -> Context:
        question_link = insert_raw_hypertext(contents, self.db, {})
        answer_link = self.db.make_promise()
        final_workspace_link = self.db.make_promise()
        scratchpad_link = insert_raw_hypertext("", self.db, {})
        new_workspace = Workspace(question_link, answer_link, final_workspace_link, scratchpad_link, [])
        new_workspace_link = self.db.insert(new_workspace)
        return Context(new_workspace_link, self.db)

    def resolve_action(self, action: Action) -> None:
        if action.branches_contexts():
            self.execute_branching_action(action)
        else:
            self.execute_nonbranching_action(action)

    def execute_nonbranching_action(self, action: Action) -> None:
        assert self.current_context is not None
        self.current_context, others = action.execute(
                self.db, self.current_context, self.current_context.workspace_link)
        self.unbranched_actions.append(action)
        self.branches.extend(others)

    def execute_branching_action(self, action: Action) -> None:
        assert self.current_context is not None

        _, branches = action.execute(
                self.db, self.current_context, self.current_context.workspace_link)
        self.unbranched_actions.append(action)

        self.cache[self.last_branching_context] = self.unbranched_actions
        self.unbranched_actions = []

        self.branches.extend(branches)

        while len(self.branches) > 0 and self.branches[-1] in self.cache:
            next_context = self.branches.pop()
            for next_action in self.cache[next_context]:
                successor, others = next_action.execute(self.db, next_context, next_context.workspace_link)
                self.branches.extend(others)
                if successor is None:
                    break
                next_context = successor
        
        if len(self.branches) == 0:
            self.current_context = None
        else:
            self.current_context = self.branches.pop()
            self.last_branching_context = self.current_context
