from collections import defaultdict, deque
from textwrap import indent
from typing import DefaultDict, Dict, Deque, Generator, List, Optional, Set, Tuple

from .datastore import Address, Datastore
from .hypertext import Workspace

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


