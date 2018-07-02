# Patchwork

![](sorted_list.gif)

This repository contains an implementation of an
[HCH](https://ai-alignment.com/humans-consulting-hch-f893f6051455) test bed.
It is intended to serve as a model for a multi-user web app, and thus explicitly
represents and manages all state in a data store.

In the terms used by Ought's [taxonomy of approaches to capability
amplification](https://ought.org/projects/factored-cognition/taxonomy),
this program implements question-answering with:

* Recursion
* Pointers
* A weak form of reflection, in which trees of workspaces can be passed around and
  inspected, but actions are not reifiable and not always inferrable. Specifically,
  pointer unlocking actions cannot be recovered.
* Caching (memoization)
* Lazy evaluation

The general idea here is that this is a system for breaking problems down into
sub-problems. Given a starting problem, a human (H) takes actions that can either
create sub-problems (contexts), unlock data (pointers), track some internal or
strategic state (scratchpads), or solve the problem (reply to the question).

We make the assumption that H is a pure function from contexts to actions. This
allows us to perform automation to avoid making unnecessary calls to H, as
seen in the "is this list sorted" demo gif above.

## Setup

In order to use this package, you'll need at least Python 3.6 and parsy 1.2.0.

You can get parsy by running `pip install -r requirements.txt`.

## Usage

To begin, run

```bash
python -m patchwork.main [optional_database_file]
```

The app can be used to answer simple questions. When the app starts, the user
will be presented with a prompt to enter a "root-level question". From here on,
the user will be presented with a sequence of “contexts”. 

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

### Taking actions

Four actions can be taken in any context:
1. `ask <subquestion>`: Ask a subquestion
2. `scratch <scratchpad_contents>`: replace the scratchpad contents with
  `<scratchpad_contents>`.
3. `unlock <pointer_id>`: Make a successor context that has
  the pointer `<pointer_id>` visible.
4. `reply <response>`: Answer the question with `<response>`

#### Hypertext syntax

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

## Implementation details

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
be redirected to the deduplicated data (even though their address does not match
the canonical address of that data).

### Hypertext

The datastore can be seen as an analogue for an HTTP server, and its contents
can be seen as analogues for HTML pages with references to other pages on that
server. Hypertext equality is based on the string that it gets converted to
when printed (with any addresses "canonicalized", i.e. replaced by the canonical
value of their corresponding canonical address).

#### Workspaces

A workspace is a structured hypertext object that contains pointers to the
data that's visible from a context: an optional predecessor, a question,
a scratchpad, and a list of subquestions with their answers and final
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

## Future Work

This system is not entirely ready for prime-time. If you play with it for long,
you are likely to uncover bugs. Furthermore, the abstractions used here are probably
not powerful enough to build a complete HCH system.

### "True" Laziness

The current system _may_ happen to avoid work that isn't necessary; however,
it doesn't track which work is actually required. It would be fairly straightforward
to add the ability to avoid doing any unnecessary work.

### "True" Reflection

The current system allows trees of workspaces to be passed around, and each workspace
includes a link to its predecessor, so some actions can be inferred. However, for all
actions to be inferred (including pointer unlocking), we would probably need to reify
the history of contexts in a way that's accessible through a pointer. This might in 
turn imply that contexts and actions should be instances of hypertext.

### Budgets

The current system does not support budgets. This naively results in cases where
infinite automation loops are possible. While we've avoided those here by implementing
an explicit check against them, strictly decreasing budgets would eliminate the
need for this complexity.

Once budgets are in place, we'll need to consider the interaction between budgets and
automation. Since budgets are part of the workspace state, differences in budgets
correspond result in cache-based automation treating the corresponding contexts as
different. This reduces the number of cache hits substantially. This could be addressed
by

1. Only showing budgets rounded to the nearest power of 10. (This is what Paul did in some implementations.)
2. Hiding the budget behind a pointer so that users can ask questions about it (e.g., "What is the nearest power of 10 for budget #b")
3. Using a more general prediction scheme instead of cache-based automation, so that some contexts are treated as sufficiently similar for automation to apply even if the budgets differ.

We should also reconsider using VOI-based budgets.

### Exceptional Cases and Speculative Execution

The current design allows the user to pass around answer pointers that have not been
completed yet. This is normally fine, but imagine that the system is somehow unable
to complete the request - maybe the question was malformed, or maybe the user didn't
have enough budget. There needs to be a way to indicate that an answer has "failed" -
otherwise, you'll end up with "What is 7 * [I can't answer that question]?"

One possibility would be to have each subquestion generate two possible resulting
contexts: a "success" and a "failure". The system could then instantiate only the more
likely of the two successors; doubling back to instantiate the other (and invalidate
work that depended on it) if it turns out to have been wrong. This is similar to how
branch prediction works in CPUs.

A generalization of this idea is to do speculative execution on the text of a
message. I.e., if the answer is commonly "The answer is #1", maybe we can just
predict that the answer has this shape (without filling in #1) and if we do the
computation and it turns out to be different, we can double back to go with the
actual response. (This may be easier if we have edits or otherwise strong reuse
of computation.)

In addition to doing speculative execution on the answer from a sub-question, we
can also do speculative execution for pointer expansions. If we have a lazy pointer
#1, we can predict what its value will be and go with that, later updating it if
we do the computation and it turns out different.

It would be good to better understand how speculative execution and full 
question-answer prediction (as in distillation) relate. Can these be built using
the same shared technology

### Multiple Sessions and Users

While the basic idea of user sessions is visible in the code as it stands today,
this is hacky and would probably not stand up to implementing a multi-user
frontend immediately. There are several questions that would need to be answered
in order to successfully manage multiple users; for example, what should happen if
a root question is already being dispatched by another user?

### Edits

Suppose you asked a question which resulted in a big tree of sub-computations. You
(or rather, your successor) then realized that there was a mistake and that you 
should have asked the question differently. In that case, reflection might help
a bit - you can ask "What is the answer to $q2 given that we previously asked
about $q1 which resulted in computation $c1?". The agents answering $q2 can then
unroll the computation $c1 and reuse some of the work. However, there is probably
some work to be done to make this as convenient as 
[incremental improvement through edits](https://ought.org/projects/factored-cognition/taxonomy#persistence).

Re-asking a question with increased budget and re-asking with a pointer to a slightly
different object are important special cases.

If it is not the case that edits can be simulated well in a system where questions
and pointer values are immutable, we should consider the pros and cons of allowing such 
edits.
