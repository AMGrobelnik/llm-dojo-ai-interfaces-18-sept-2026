---
name: amg-open-img-ubuntu
description: "Displays existing image files on Ubuntu GNOME/Wayland by copying them into an isolated batch folder and launching the loupe viewer with the WAYLAND_DISPLAY, XDG_RUNTIME_DIR and DBUS_SESSION_BUS_ADDRESS exports the terminal lacks. Use whenever a generated figure, screenshot or any image already on disk has to be put in front of the user to look at, or arrow-navigated as a batch. Triggers: show the image, open the picture, view the screenshot, arrow through these images, loupe, GNOME image viewer, Wayland display vars, image viewer will not open. NOT for: creating or editing any image — generation is aii-concept-fig-gen, numeric charts are aii-data-fig-gen, and multi-round variant batches are amg-iter-image-gen-human; NOT for capturing a fresh screenshot of a running UI, which is amg-frontend-testing."
---

## Environment

Ubuntu GNOME on Wayland. The terminal (Ghostty) does NOT have display env vars set, so you must export them manually.

## Required Env Vars

Every `loupe` command must be prefixed with:

```bash
export WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
```

## Image Viewer

Use `loupe` (GNOME Image Viewer). It is installed at `/usr/bin/loupe`.

**Important**: loupe shows ALL images in the same directory. To control exactly which images the user sees, copy them into an isolated batch folder first.

## Batch Viewing Pattern

When showing a batch of images to the user:

1. Create a temp batch subfolder inside the working directory:
   ```bash
   mkdir -p /path/to/working/dir/temp/batch_description
   ```

2. Copy only the images you want to show into that folder:
   ```bash
   cp /path/to/image1.png /path/to/image2.png /path/to/working/dir/temp/batch_description/
   ```

3. Open the first image with loupe (user can arrow-key through the rest):
   ```bash
   export WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
   setsid loupe "/path/to/working/dir/temp/batch_description/image1.png" &>/dev/null &
   ```

The user can then navigate through only the batch images using arrow keys in loupe.

## Single Image

For a single image, still use a batch folder (otherwise loupe shows everything in the directory):

```bash
export WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
mkdir -p /path/to/working/dir/temp/single_view
cp /path/to/image.png /path/to/working/dir/temp/single_view/
setsid loupe "/path/to/working/dir/temp/single_view/image.png" &>/dev/null &
```

## Cleanup

Clean up temp batch folders when done or when creating new batches:

```bash
rm -rf /path/to/working/dir/temp/
```

## Full Example

```bash
# Show user 3 generated figures
mkdir -p ./temp/batch_figures
cp figure_v1.png figure_v2.png figure_v3.png ./temp/batch_figures/

export WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
setsid loupe "./temp/batch_figures/figure_v1.png" &>/dev/null &
```
