from collections import defaultdict, deque
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

        print()
        print("workspace ", workspace_link)
        print("predecessor ", workspace.predecessor_link)
        print("question ", workspace.question_link)
        print("scratchpad ", workspace.scratchpad_link)
        print("subquestions ", workspace.subquestions)
        print("unlocked ", self.unlocked_locations)
        print()


        self.pointer_names, self.name_pointers = self._name_pointers(self.workspace_link, db)
        self.display = self.to_str(db)

    def _zip_unlocked_with_workspace(
            self,
            workspace_link: Address,
            db: Datastore,
            ) -> Generator[Tuple[Address, Address], None, None]:
        frontier = deque([(self.workspace_link, workspace_link)])
        seen = set(frontier)
        while len(frontier) > 0:
            my_link, your_link = frontier.popleft()
            if my_link in self.unlocked_locations:
                yield (my_link, your_link)
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
        if workspace_root.predecessor_link is not None:
            assign(workspace_root.predecessor_link, "$predecessor")
        assign(workspace_root.question_link, "$question")
        assign(workspace_root.scratchpad_link, "$scratchpad")

        for i, subquestion in enumerate(workspace_root.subquestions, start=1):
            # Pyre doesn't like tuple destructuring in loops apparently.
            q, a, w = subquestion
            assign(q, "$q{}".format(i))
            assign(a, "$a{}".format(i))
            assign(w, "$w{}".format(i))

        count = 0
        for my_link, your_link in self._zip_unlocked_with_workspace(workspace_link, db):
            your_page = db.dereference(your_link)
            for visible_link in your_page.links():
                if visible_link not in pointers:
                    count += 1
                    assign(your_link, "${}".format(count))

        return pointers, backward_pointers


    def unlocked_locations_from_workspace(
            self,
            workspace_link: Address,
            db: Datastore,
            ) -> Set[Address]:
        for mylink, link in self._zip_unlocked_with_workspace(workspace_link, db):
            print("Mine ", mylink, "new ", link)

        result = set(link for (_, link) in self._zip_unlocked_with_workspace(workspace_link, db))
        return result

    def name_pointers_for_workspace(
            self,
            workspace_link: Address,
            db: Datastore
            ) -> Dict[str, Address]:
        return self._name_pointers(workspace_link, db)[1]


    def to_str(self, db: Datastore) -> str:
        INLINE_FMT = "[{pointer_name}: {content}]"
        CONTEXT_FMT = "{predecessor}\n\n{question}\n\n{scratchpad}\n\n{subquestions}\n"

        # We need to construct this string in topological order since pointers
        # are substrings of other unlocked pointers. Since everything is immutable
        # once created, we are guaranteed to have a DAG.
        include_counts: DefaultDict[Address, int] = defaultdict(int)

        for _, link in self._zip_unlocked_with_workspace(self.workspace_link, db):
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
            subquestion_builder.append("{}.\n  {}\n  {}\n  {}".format(i, q_text, a_text, w_text))
        subquestions = "\n".join(subquestion_builder)

        if workspace.predecessor_link is None:
            predecessor = ""
        else:
            predecessor = link_texts[workspace.predecessor_link]

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


class AskSubquestion(Action):
    def __init__(self, question_text: str) -> None:
        self.question_text = question_text

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
        sub_workspace = Workspace(subquestion_link, answer_link, final_sub_workspace_link, scratchpad_link, [])
        sub_workspace_link = db.insert(sub_workspace)


        current_workspace = db.dereference(current_workspace_link)
        new_subquestions = (current_workspace.subquestions +
                [(subquestion_link, answer_link, final_sub_workspace_link)])
        successor_workspace = Workspace(
                current_workspace.question_link,
                current_workspace.answer_promise,
                current_workspace.final_workspace_promise,
                current_workspace.scratchpad_link,
                new_subquestions,
                predecessor_link=current_workspace_link)

        successor_workspace_link = db.insert(successor_workspace)

        print("Old unlocked locations: ", context.unlocked_locations)
        print("New unlocked locations: ", context.unlocked_locations_from_workspace(successor_workspace_link, db))

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

    def execute(
            self,
            db: Datastore,
            context: Context,
            current_workspace_link: Address,
            ) -> Tuple[Optional[Context], List[Context]]:

        current_workspace = db.dereference(current_workspace_link)
        # final_workspace_promise and answer_promise aren't in
        # workspace.links(), so this is fine.
        answer_successors = db.resolve_promise(
                    current_workspace.answer_promise,
                    create_raw_hypertext(
                        self.reply_text,
                        db,
                        context.name_pointers_for_workspace(
                            current_workspace_link,
                            db
                            )
                        )
                    )
        workspace_successors = db.resolve_promise(
                current_workspace.final_workspace_promise,
                current_workspace)

        return (None, answer_successors + workspace_successors)


class Unlock(Action):
    def __init__(self, unlock_text: str) -> None:
        self.unlock_text = unlock_text

    def execute(
            self,
            db: Datastore,
            context: Context,
            current_workspace_link: Address,
            ) -> Tuple[Optional[Context], List[Context]]:

        pointer_address = context.name_pointers_for_workspace(
                current_workspace_link,
                db
                )[self.unlock_text]

        new_unlocked_locations = set(context.unlocked_locations_from_workspace(
                current_workspace_link, db))

        new_unlocked_locations.add(pointer_address)

        successor_context = Context(
                current_workspace_link, db, unlocked_locations=new_unlocked_locations)

        if db.is_fulfilled(pointer_address):
            return (None, [successor_context])

        db.register_promisee(pointer_address, successor_context)
        return (None, [])


class Scratch(Action):
    def __init__(self, scratch_text: str) -> None:
        self.scratch_text = scratch_text

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
                predecessor_link=current_workspace_link)

        successor_workspace_link = db.insert(successor_workspace)
        print("Old unlocked locations: ", context.unlocked_locations)
        print("New unlocked locations: ", context.unlocked_locations_from_workspace(current_workspace_link, db))
        print("New scratchpad link: ", new_scratchpad_link)

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
    def __init__(self, db: Datastore) -> None:
        self.db = db
        self.pending_contexts: Deque[Context] = deque()
        self.cache: Dict[Context, Action] = {}

    def ask_root_question(self, contents: str) -> None:
        question_link = insert_raw_hypertext(contents, self.db, {})
        print("$Q: ", question_link)
        answer_link = self.db.make_promise()
        print("$A: ", answer_link)
        final_workspace_link = self.db.make_promise()
        print("$F: ", final_workspace_link)
        scratchpad_link = insert_raw_hypertext("", self.db, {})
        print("$S: ", scratchpad_link)
        new_workspace = Workspace(question_link, answer_link, final_workspace_link, scratchpad_link, [])
        new_workspace_link = self.db.insert(new_workspace)
        print("$W: ", new_workspace_link)
        self.pending_contexts.append(Context(new_workspace_link, self.db))

    def resolve_action(self, context: Context, action: Action) -> None:
        self.cache[context] = action
        self.execute_action(context, action)

    def execute_action(self, context: Context, action: Action) -> None:
        resulting_contexts = action.execute(self.db, context, context.workspace_link)
        if resulting_contexts[0] is not None:
            self.pending_contexts.appendleft(resulting_contexts[0])

        self.pending_contexts.extend(resulting_contexts[1])

    def choose_context(self) -> Context:
        while self.pending_contexts[0] in self.cache:
            pending_context = self.pending_contexts.popleft()
            self.execute_action(pending_context, self.cache[pending_context])

        return self.pending_contexts.popleft()
