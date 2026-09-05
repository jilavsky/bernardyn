# Bernardyn workflow

## The short version

A **workspace** is the complete editing session currently open in Bernardyn.
It can contain several graph tabs and one shared catalog of imported datasets.
A **graph** is one tab: its chosen data, transform, axes, styles, legend,
annotations, and (where applicable) 3D camera settings.

A **graph package** is a `.bernardyn.h5` file containing one graph. A
**workspace package** is the same `.bernardyn.h5` format containing every
graph in a workspace. Both embed the data required to reopen their graph(s);
the original data files are not needed after saving.

## Normal use

1. Start Bernardyn. It opens a new, unsaved workspace with one graph tab.
2. Use **File → Open data…** or **File → Open folder…** to select source data.
   Imported curves join the dataset catalog and are added to the active graph.
3. Create additional graph tabs with **Graph → New 2D graph**, **New 3D
   waterfall**, or **New 3D surface**. A dataset may be used in more than one
   graph without being duplicated in the workspace.
4. Edit each graph independently in the inspector.
5. For your continuing multi-graph session, use **File → Save workspace
   package as…**. This writes every graph and deduplicates shared data.
6. To reopen that session later, use **File → Open package…** and select the
   `.bernardyn.h5` file. This replaces the current workspace after the normal
   unsaved-work confirmation.

## When to save a graph package

Use **File → Save graph package…** to make a compact, self-contained archive
or shareable copy of the active graph only. It includes only the datasets used
by that graph. The recipient opens it with **File → Open package…** just like a
workspace package.

Saving one graph does not alter or discard other graph tabs in the current
workspace. It is best treated as an exported graph archive; use a workspace
package for the master editable session.

## Importing instead of opening

Use **File → Import graph from package…** when you want to bring one or more
graphs from a package into the workspace already open. Bernardyn copies only
the imported graphs and their referenced data. Datasets already present are
reused only when their UUID and checksum agree.

## Save and Save As

- **Save** updates the currently opened or previously saved workspace package.
- **Save workspace package as…** creates a new workspace package and makes it
  the ongoing save destination.
- **Save graph package…** writes only the active graph. It is intentionally
  separate from the workspace Save destination.

## Graph templates are different

A `.bernardyn-template.json` file contains formatting and graph settings but
no data, snapshots, or source paths. Apply a template to give a graph a
consistent appearance; save a graph/workspace package when the data must travel
with it.
