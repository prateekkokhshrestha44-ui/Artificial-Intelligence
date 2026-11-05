---
name: note-taking
description: How to write project notes: where to save them, how to name the file, and the required layout. Use when asked to write, save or record a note.
---
Project notes follow this convention:

1. Save the note inside the `notes/` folder.
2. The file name is the title in lowercase, words joined by hyphens, ending in `.md`.
   Example: the title "Budget Review" becomes `notes/budget-review.md`.
3. The file content has exactly this shape (replace the angle-bracket parts):

# <Title exactly as given>
Status: draft

<the note text, one or two sentences>

4. Add no other sections.
5. Write the file with write_file, then finish.
