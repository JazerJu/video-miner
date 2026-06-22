# Tags Management

Tags Management lets you create, edit, and delete video tags. A tag has a name and color. The list supports multi-select batch deletion.

## Create a tag

| Setting | Type | Default | Description |
| --- | --- | --- | --- |
| Tag name | Text input | Empty | Name for the new tag. Press Enter or click Create to submit. |
| Tag color | Color picker | Random suggested color | Color for the new tag, shown as a hex value. |
| Recommended Colors | Button group | Preset color list | Options are `#3B82F6`, `#14B8A6`, `#10B981`, `#84CC16`, `#F59E0B`, `#F97316`, `#EF4444`, `#EC4899`, `#8B5CF6`, `#6366F1`, `#06B6D4`, and `#64748B`. |
| Random | Button | None | Generates a suggested random color. |
| Create | Button | None | Creates the tag. Disabled when the name is empty. |

## Tag list

| Setting | Type | Default | Description |
| --- | --- | --- | --- |
| Tag List | List | Empty | Shows all tags and the tag count. |
| Select tag | Checkbox | Unchecked | Selects one or more tags for batch deletion. |
| Edit | Button | None | Enters edit mode for tag name and color. |
| Save edit | Button | None | Saves tag name and color changes. |
| Cancel edit | Button | None | Discards the current edit. |
| Delete | Button | None | Deletes one tag and removes it from all videos. |
| Batch Delete | Button | None | Deletes selected tags and removes them from all videos. |
| Clear selection | Button | None | Clears the current selected tags. |

## How to edit a tag

1. Click Edit in the "Tag List".
2. Change the name or color.
3. Click Save.

## How to delete tags

1. To delete one tag, click "Delete" on the right side of that tag.
2. To delete multiple tags, select them and click batch "Delete".
3. Confirm the action in the confirmation dialog.

> The current settings panel does not have a "Merge Tags" control. The backend API already supports merging, and the control will be added in a future update.

---

[Back to English docs](../) | [Previous: Video Understanding](../video-understanding/) | Next: none
