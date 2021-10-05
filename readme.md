# PyPacker: a dumb little script for turning Python apps into standalone executable packages on Windows

PyPacker is my attempt at creating a way to make Python apps fully portable on Windows. It does this by performing *live program analysis* to determine what to pack up.

## Rationale

Most systems for turning Python apps into standalone programs analyze the program to determine what and how to pack things up, but don't actually run the program in question. PyPacker runs the program and makes a record of all the imports actually used during the program's lifetime.

The downside of this approach is that you have to perform at least one run with the program that provides the broadest possible program coverage -- e.g., all imports are fully executed, etc. The upside is that PyPacker knows what to copy. Also, your trace files can be reused as long as no new program components have been added in the meantime.

## Usage

Run it like so:

`py -m pypacker -a entry_point.py`

where `entry_point.py` is the entry point to your application.

The application will launch. Run it and make sure you use as much of its functionality as possible.

When your program exits, PyPacker it will generate a `tracefile.json` file that can be re-used for future runs (by just typing `py -m pypacker` in that directory). It will then package your application for redistribution.

The resulting redistributable will be placed in the `dist` subdirectory. A zipped version of the redistributable directory is also provided.

## What PyPacker tries to do

* The main program tree is turned into a `.zip` file (of `.pyc` files).
* Any non-Python files in the main program tree are copied into a parallel directory off the root of the `dist` directory.
* Usage of `.pyd` files and some `.dll`s are automatically detected as well and copied.
* Third-party packages are also included.
* Both console and windowed executables are provided.

External assets, like files loaded by the program itself (not imports) are not detected. I'm adding mechanisms to copy them in manually by modifying the tracefile.

## Caveats

Very buggy. Drastically incomplete. For instance, stuff like NumPy probably doesn't work yet.

## License

MIT