# Rudimentary Pure HCH

This repository contains an implementation of an
[HCH](https://ai-alignment.com/humans-consulting-hch-f893f6051455) test bed.

In the terms used by the
[Ought Taxonomy of approaches to capability
amplification](https://ought.org/projects/factored-cognition/taxonomy),
this program implements:

* One-shot question answering
* Recursion
* Pointers
* A weak form of reflection, in which workspaces can be passed around and
   inspected, but actions are not reifiable and not always inferrable.
   Specifically, pointer unlocking actions cannot be recovered.
* Caching
* Lazy Evaluation

## Setup

In order to use this package, you'll need at least Python 3.6 and parsy 1.2.0.

## Usage

To begin, run

```bash
python -m pure_hch.main
```

### Interpreting a context
At any given moment during the program's execution, you're looking at a context.
A context can display four fields:

1. A pointer to a predecessor workspace
2. A pointer to a question to be answered (unlocked)
3. A pointer to a scratchpad (unlocked) where intermediate work can be cached
4. A list of pointers to subquestions. The subquestions themselves are unlocked,
   but the answers and workspaces used to compute those answers are not.

#### Hypertext in contexts
Contexts contain pointers, which can be thought of as links to pages in a web of
hypertext. They are abstract references to data. A pointer can either
be "locked" or "unlocked". Locked pointers appear as `$<id>`, where `<id>` is either
a number, or a special identifier followed by a number. So `$12` is a locked pointer,
`$q1` is the locked pointer to your first subquestion, `$a1` is the locked pointer to
the first subquestion's answer, and `$w1` is the locked pointer to the workspace that
generated the first subquestion's answer.

Unlocked pointers appear inside square brackets, with the pointer id prepended to
the content of the data: `[$1: Hello, world]` represents an unlocked pointer to
hypertext containing the string `Hello, world`. Hypertext can either represent
a workspace (as in the `$w1` example), or can be "raw", representing some
unstructured text.

### Taking Actions

Four actions can be taken in any context:
1. `ask <subquestion>`: Ask a subquestion
2. `scratch <scratchpad_contents>`: replace the scratchpad contents with
  `<scratchpad_contents>`.
3. `unlock <pointer_id>`: Make a successor context that has
  the pointer `<pointer_id>` visible.
4. `reply <response>`: Answer the question with `<response>`

#### Hypertext Syntax

The `ask`, `scratch`, and `reply` commands all accept hypertext as an
argument. The hypertext you specify here is similar to the hypertext
that appears throughout the context, but is slightly different.

In particular, expanded pointers in your hypertext should not have
identifier prefixes. For example, you might
`ask is the list [[a] [[b] [[c] [[d] []]]]] sorted?`. Otherwise, the hypertext
you construct is syntactically identical to the hypertext in a context.

The `unlock` action accepts a pointer exactly as it appears in the context:
For example, `unlock $w1`.

> USAGE NOTE: This system is _lazy_. This means that unlocking a pointer automatically
puts the successor context on hold until at least the unlocked result is ready. However,
locked pointers can be _passed around_ arbitrarily before being unlocked. So if
I want to ask three questions in sequence, I can pass the answer of the first
to the second, and the answer of the second to the third, without unlocking anything,
and without being put on hold.  When I unlock the third answer, my successor will not
wake up until that answer is actually available.

## Implementation Details

The system is implemented using the following concepts. It is intended to
serve as a model for a multi-user web app version, in which the database
stores the contents of the datastore and the scheduler.

### Content-addressed datastore

The Datastore and Address classes are the mechanism used for lazily storing
references to deduplicated data. Addresses are basically unique identifiers,
while the datastore is used to keep track of both (a) what data exists, and
(b) what data is pending (and who is waiting on it).

When duplicate data is inserted, the address of the original data is returned.
If a promise would be fulfilled with duplicate data, the promise is added to
a list of aliases, such that anything that tries to refer to that promise will
be redirected to the deduplicated data (even though their addres does not match
the canonical address of that data).

### Hypertext

The datastore can be seen as an analogue for an HTTP server, and its contents
can be seen as analogues for HTML pages with references to other pages on that
server. Hypertext equality is based on the string that it gets converted to
when printed (with any addresses "canonicalized" (replaced by the canonical
value of their corresponding canonical address)).

#### Workspaces

A workspace is a structured hypertext object, that contains pointers to the
data that's visible from a context: an optional predecessor, a question,
a scratchpad, and a collection of subquestions with their answers and final
workspaces.

### Context

A context is a view of a workspace that also contains a set of pointers that
are unlocked in that context. The pointers that are unlocked are replaced
in the textual representation by text in square brackets. By default, the
workspace's question, scratchpad, and subquestions are unlocked.

### Action

Action objects represent the actions that can be taken by the user:
There is one class for each action that can be taken.

Actions are not taken immediately on creation; they are executed by the
scheduler when the scheduler sees fit, making updates to the datastore
and producing a new set of contexts.

### Scheduler

The scheduler is the part of the system that decides when to execute
actions, and which context to show to which user and when. It also
manages automation, by remembering contexts and taking its own
actions under the assumption that the user is a pure function from
context to action.
