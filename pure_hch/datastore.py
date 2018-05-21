import uuid

from collections import defaultdict

from typing import Any, DefaultDict, Dict, List, Set


# REVISIT: Plausibly this should be generic over the addressed
# content.
class Address(object):
    def __init__(self, db: "Datastore") -> None:
        self.location = uuid.uuid1()
        self.db = db

    def __hash__(self) -> int:
        return hash(self.location)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Address):
            return False
        return self.location == other.location

    def __str__(self) -> str:
        return repr(self)

    def __repr__(self) -> str:
        return "Address({})".format(self.location)


class Datastore(object):
    def __init__(self) -> None:
        self.content: Dict[Address, Any] = {} # Map from canonical address to content
        self.canonical_addresses: Dict[Any, Address] = {} # Map from content to canonical address
        self.promises: Dict[Address, List[Any]] = {} # Map from alias to list of promisees
        self.aliases: Dict[Address, Address] = {} # Map from alias to canonical address

    def dereference(self, address: Address) -> Any:
        return self.content[self.canonicalize(address)]

    def canonicalize(self, address: Address) -> Address:
        if address in self.aliases:
            return self.aliases[address]
        elif address in self.content or address in self.promises:
            return address
        else:
            raise KeyError("Don't have that address")

    def make_promise(self) -> Address:
        address = Address(self)
        self.promises[address] = []
        return address

    def register_promisee(self, address: Address, promisee: Any) -> None:
        self.promises[address].append(promisee)

    def resolve_promise(self, address: Address, content: Any) -> List[Any]:
        assert address in self.promises, "{} not in promises".format(address)
        if content in self.canonical_addresses:
            self.aliases[address] = self.canonical_addresses[content]
        else:
            self.content[address] = content
            self.canonical_addresses[content] = address
        promisees = self.promises[address]
        del self.promises[address]
        return promisees

    def insert(self, content: Any) -> Address:
        if content in self.canonical_addresses:
            return self.canonical_addresses[content]

        address = self.make_promise()
        self.resolve_promise(address, content)
        return address

    def is_fulfilled(self, address: Address) -> bool:
        address = self.canonicalize(address)
        return address in self.content


class TransactionAccumulator(Datastore):
    # A way of performing ACID-ish transactions against the Datastore
    def __init__(self, db: Datastore) -> None:
        self.db = db
        # Promises that were made and not fulfilled in this transaction
        self.new_promises: Dict[Address, List[Any]] = {}

        # Former promises that have been resolved by this transaction
        self.resolved_promises: Set[Address] = set()

         # Registered promisees on existing promises in this transaction
        self.additional_promisees: DefaultDict[Address, List[Any]] = defaultdict(list)

        # Content that is new and complete in this transaction
        self.new_content: Dict[Address, Any] = {}

         # inverse map of new_content
        self.new_canonical_addresses: Dict[Any, Address] = {}

        # aliases that were created in this transaction
        self.new_aliases: Dict[Address, Address] = {}

    def dereference(self, address: Address) -> Any:
        address = self.canonicalize(address)
        if address in self.new_content:
            return self.new_content[address]
        else:
            return self.db.content[address]

    def canonicalize(self, address: Address) -> Address:
        if address in self.new_aliases:
            return self.new_aliases[address]
        elif address in self.db.aliases:
            return self.db.aliases[address]
        elif address in self.new_content or address in self.new_promises:
            return address
        elif address in self.db.content or address in self.db.promises:
            return address
        else:
            raise KeyError("Don't have that address")

    def make_promise(self) -> Address:
        address = Address(self)
        self.new_promises[address] = []
        return address

    def register_promisee(self, address: Address, promisee: Any) -> None:
        if address in self.resolved_promises:
            raise ValueError("Promise already resolved")
        if address in self.new_promises:
            self.new_promises[address].append(promisee)
        elif address in self.additional_promisees:
            self.additional_promisees[address].append(promisee)
        elif address in self.db.promises:
            self.additional_promisees[address] = [promisee]
        else:
            raise ValueError("address not a promise")

    def resolve_promise(self, address: Address, content: Any) -> List[Any]:
        assert address in self.new_promises or address in self.db.promises, "{} not in promises".format(address)
        if content in self.db.canonical_addresses:
            self.new_aliases[address] = self.db.canonical_addresses[content]
        elif content in self.new_canonical_addresses:
            self.new_aliases[address] = self.new_canonical_addresses[content]
        else:
            self.new_content[address] = content
            self.new_canonical_addresses[content] = address

        if address in self.db.promises:
            promisees = self.db.promises[address]
            promisees.extend(self.additional_promisees.get(address, []))
            self.resolved_promises.add(address)
        else:
            promisees = self.new_promises[address]
            del self.promises[address]
        return promisees

    def insert(self, content: Any) -> Address:
        if content in self.canonical_addresses:
            return self.canonical_addresses[content]
        if content in self.db.canonical_addresses:
            return self.db.canonical_addresses[content]

        address = self.make_promise()
        self.resolve_promise(address, content)
        return address

    def is_fulfilled(self, address: Address) -> bool:
        address = self.canonicalize(address)
        return address in self.new_content or address in self.db.content

    def commit(self) -> None:
        self.db.promises.update(self.new_promises)
        for a, l in self.additional_promisees.items():
            self.db.promises[a].extend(l)
        self.db.content.update(self.new_content)
        self.db.canonical_addresses.update(self.new_canonical_addresses)
        self.db.aliases.update(self.new_aliases)
        for a in self.resolved_promises:
            del self.db.promises[a]
