import sys
import pathlib
import shutil
import zipfile
import py_compile
import os
import json

if len(sys.argv) == 1:
    print(
        """
usage: pypacker
    -a <module> -- analyze module
    -v -- for verbose output
"""
    )

# TODO: "simple" mode - just copy everything, no analysis

verbose = "-v" in sys.argv

vprint = lambda *a: None
if verbose:
    vprint = lambda *a: print(*a)


class IniFileMissing(Exception):
    pass


class Analysis:
    def __init__(self, app_name):
        self.app_name = app_name
        self.analyze()

    def generate_analysis_script(self):
        temp = f"""
try:
    import {self.app_name}
except BaseException:
    pass

import sys

run_modules = set(sys.modules.keys()) #-original_modules

import json
import types

final_modules = []

for m in run_modules:
    if m == "{self.app_name}":
        continue
    if isinstance(sys.modules[m], type):
        continue
    if m in sys.builtin_module_names:
        continue
    if getattr(sys.modules[m], "__file__", None) is None:
        continue
    final_modules.append([m, sys.modules[m].__file__])
    
with open("{self.app_name}.tmp","w") as f:
    json.dump(sorted(final_modules), f)
        """

        with open(f"{self.app_name}_analysis.py", "w") as f:
            f.write(temp)

    def delete_analysis_script(self):
        pathlib.Path(f"{self.app_name}_analysis.py").unlink()

    def delete_tempdata(self):
        pathlib.Path(f"{self.app_name}.tmp").unlink()

    def analyze(self):
        self.standalone_file = None

        as_module = pathlib.Path(self.app_name)

        print("Looking for", as_module.absolute())

        if as_module.is_dir():
            self.standalone_file = False
        elif as_module.is_file():
            self.standalone_file = True
        elif (as_module / ".py").is_file():
            self.standalone_file = True

        if self.standalone_file is None:
            raise Exception("Couldn't determine what to import")

        print(
            f"Importing {self.app_name} as {'file' if self.standalone_file else 'module'}"
        )

        import site
        import json
        import subprocess

        print(f"Starting run for {self.app_name}")

        self.generate_analysis_script()

        subprocess.run(["py", f"{self.app_name}_analysis.py"])

        site_pkgs = site.getsitepackages()
        lib_dir = pathlib.Path(subprocess.__file__).parent

        print(f"Starting analysis for {self.app_name}")

        root_app_dir = pathlib.Path(f"{self.app_name}.tmp").parent.absolute()

        with open(f"{self.app_name}.tmp") as f:
            loaded_modules = json.load(f)

        std_lib = []
        app_lib = []
        binaries = []
        app_modules = []

        for m, mn in loaded_modules:
            if mn.endswith(".pyd") or mn.endswith(".dll"):
                binaries.append(mn)
            elif mn.startswith(f"{lib_dir}\\"):
                t = mn.replace(f"{lib_dir}\\", "")
                std_lib.append(t)
            else:
                for p in site_pkgs[1:]:
                    if mn.startswith(p + "\\"):
                        t = mn.replace(p + "\\", "")
                        app_lib.append(t)
                    else:
                        t = mn.replace(f"{root_app_dir}\\", "")
                        app_modules.append(t)

        self.delete_tempdata()
        self.delete_analysis_script()

        output = {
            "app": self.app_name,
            "std_lib": sorted(set(std_lib)),
            "app_lib": sorted(set(app_lib)),
            "app_modules": sorted(set(app_modules)),
            "binaries": sorted(set(binaries)),
        }

        # TODO:
        # migrate copyfile information from old json

        filename = f"tracefile.json"

        with open(filename, "w") as f:
            json.dump(output, f, indent=4)

        print("Analysis done")

        return filename


class AppInfo:
    def __init__(self, config_file=None):

        self.py_version = f"python{sys.version_info[0]}{sys.version_info[1]}"

        if config_file is None:
            self.setup_no_config()
        else:
            self.setup(config_file)

    def setup_no_config(self):
        raise NotImplementedError

    def setup(self, config_file: dict):

        self.use_tk = False

        self.standalone = False

        self.appdir = config_file["app"]
        if self.appdir.endswith(".py"):
            self.app_title = self.appdir.rsplit(".py", 1)[0]
            self.standalone = True
        else:
            self.app_title = self.appdir
        if self.standalone:
            self.boot = f"import {self.app_title}\nquit()"
        else:
            self.boot = f"import {self.app_title}"

        self.abs_root_path = pathlib.Path(".").absolute()

        self.stdlib = config_file["std_lib"]
        self.app_lib = config_file["app_lib"]
        self.app_modules = config_file["app_modules"]
        self.lib_dirs = config_file.get("lib_dirs", [])
        self.binaries = config_file.get("binaries", [])

        self.copy_files = config_file.get("copy")
        self.exclude = set(config_file.get("exclude", []))
        self.app_exclude = set(config_file.get("app_exclude", []))

    def create_dirs(self):

        self.path_to_original_executable = pathlib.Path(sys.base_prefix)
        self.path_to_original_libs = self.path_to_original_executable / "Lib"
        self.path_to_venv_libs = pathlib.Path(sys.prefix, "Lib", "site-packages")
        self.build_path = pathlib.Path("dist")

        print(f"Creating build directory {self.build_path}")

        if self.build_path.exists():
            shutil.rmtree(self.build_path)
        self.build_path.mkdir(parents=True)

        self.lib_target_path = pathlib.Path(self.build_path, ".data")
        if self.lib_target_path.exists():
            shutil.rmtree(self.lib_target_path)
        self.lib_target_path.mkdir(parents=True)

    def copy_base_files(self):

        print("Copying base files")

        base_files = ["python.exe", "pythonw.exe", f"{self.py_version}.dll"]

        for file in base_files:
            shutil.copy(pathlib.Path(self.path_to_original_executable, file), self.build_path)

        target_path_for_base_files = self.lib_target_path.parts[-1]

        output = [
            ".",
            f"{target_path_for_base_files}",
            f"{target_path_for_base_files}\\{self.py_version}.zip",
            f"{target_path_for_base_files}\\pkg.zip",
            f"{target_path_for_base_files}\\app.zip",
            "",
            "import site"
        ]

        with open(self.build_path / f"{self.py_version}._pth", "w") as f:
            for line in output:
                f.write(line)
                f.write("\n")

    def create_stdlib_archive(self):

        print("Creating stdlib archive")

        self.stdlib_zip = zipfile.ZipFile(
            self.lib_target_path / f"{self.py_version}.zip",
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
        )

        self.stdlib.extend(self.binaries)
        self.stdlib.extend(["../DLLS/libffi-7.dll", "encodings/cp437.py"])
        all_libs = set(self.stdlib)

        for lib in all_libs:
            if not (self.path_to_original_libs / lib).exists():
                print(f"\tWarning: {lib} not found")
                continue
            if lib in self.exclude:
                vprint("\tExcluding", lib)
                continue
            if lib.endswith(".dll"):
                shutil.copy(self.path_to_original_libs / lib, self.lib_target_path)
            elif lib.endswith(".pyd"):
                if lib.endswith("_tkinter.pyd"):
                    self.use_tk = True
                if lib.startswith(str(self.abs_root_path)):
                    target_path = pathlib.Path(lib.replace(str(self.abs_root_path), ""))
                    target_directory = self.build_path / str(
                        target_path.parent.name
                    )
                    if not target_directory.exists():
                        target_directory.mkdir(parents=True)
                    shutil.copy(lib, target_directory)
                else:
                    shutil.copy(lib, self.lib_target_path)
            else:
                compiled = py_compile.compile(self.path_to_original_libs / lib, optimize=2)
                self.stdlib_zip.write(
                    compiled,
                    lib + "c",
                )

    def add_libraries(self):

        print("Adding libraries")

        self.pkgzip = zipfile.ZipFile(
            self.lib_target_path / "pkg.zip", mode="w", compression=zipfile.ZIP_DEFLATED
        )

        all_libs = set()

        for file in self.app_lib:
            all_libs.add(pathlib.Path(self.path_to_venv_libs, file.split("\\",1)[0]))
            outfile = pathlib.Path(self.path_to_venv_libs, file)
            compiled = py_compile.compile(outfile, optimize=2)
            self.pkgzip.write(
                compiled,
                pathlib.Path(file + "c"),
            )

        self.pkgzip.close()

        for libpath in all_libs:
            for path, _, files in os.walk(libpath):
                for f in files:
                    if not f.endswith((".py", ".pyc")):
                        path_parent = pathlib.Path(libpath).parent
                        # XXX
                        ppath = path.replace(str(path_parent)+"\\","")
                        target_directory = pathlib.Path(
                            self.build_path,
                            ppath
                        )
                        if not target_directory.exists():
                            target_directory.mkdir(parents=True)
                        shutil.copy(
                            pathlib.Path(path, f),
                            target_directory
                        )
                        # print (">>", pathlib.Path(path, f), target_directory)

    def add_app_libraries(self):

        print("Adding app libraries")

        self.app_zip = zipfile.ZipFile(
            self.lib_target_path / "app.zip", "w", compression=zipfile.ZIP_DEFLATED
        )

        all_paths = set()

        for file in self.app_modules:
            if any(file.startswith(x) for x in self.app_exclude):
                vprint("Excluding", file)
            path_to_file = pathlib.Path(file)
            if str(path_to_file.parent) != ".":
                all_paths.add(path_to_file.parent)
            if not path_to_file.exists():
                continue
            compiled = py_compile.compile(str(path_to_file.absolute()), optimize=2)
            self.app_zip.write(compiled, f"{file}c")

        ap2 = set()
        for p in all_paths:
            for path, _, files in os.walk(p):
                if not path.endswith("__pycache__"):
                    ap2.add(path)

        for dir in ap2:
            for file in pathlib.Path(dir).glob("*"):
                if file.is_file():
                    if not file.suffix == ".py":
                        target = pathlib.Path(self.build_path, dir)
                        if not target.exists():
                            target.mkdir(parents=True)
                        shutil.copy(file, target)

        self.app_zip.close()

    def add_site_customization(self):

        print("Adding site customization")

        self.stdlib_zip.writestr("sitecustomize.py", self.boot)
        self.stdlib_zip.close()

        if self.copy_files:
            print("Copying any additional files")
            for src_file, dest in self.copy_files:
                srcs = pathlib.Path().glob(src_file)
                target = self.build_path / dest
                if not target.exists():
                    target.mkdir()
                for src in srcs:
                    vprint("\t", src)
                    shutil.copy(src, target)

    def rename_execs(self):

        for exe, extension in (("pythonw.exe", ".exe"), ("python.exe", "_console.exe")):
            pathlib.Path(self.build_path, exe).rename(
                self.build_path / f"{self.app_title}{extension}"
            )

    def make_dist_zipfile(self):

        print("Creating distribution zip file")

        self.dist_zip = zipfile.ZipFile(
            f"{self.app_title}.zip", "w", compression=zipfile.ZIP_DEFLATED
        )

        for path, _, files in os.walk(self.build_path):
            p = pathlib.Path(path).parts[1:]
            for f in files:
                self.dist_zip.write(pathlib.Path(path, f), pathlib.Path(*p, f))

    def add_special_libs(self):

        if self.use_tk:
            tk_src = pathlib.Path(self.path_to_original_executable, "tcl")
            tk_dest = pathlib.Path(self.build_path, "lib")
            shutil.copytree(tk_src, tk_dest)
            dll_src = pathlib.Path(self.path_to_original_executable, "DLLs")
            for f in dll_src.glob("t*.dll"):
                shutil.copy(f, self.lib_target_path)
            unneeded_lib = tk_dest.glob("*.lib")
            for f in unneeded_lib:
                f.unlink()


def main():

    analyze = None
    try:
        analyze = sys.argv.index("-a")
    except ValueError:
        pass

    if analyze:
        analysis = Analysis(sys.argv[analyze + 1])

    config_file = "tracefile.json"

    try:
        c_index = sys.argv.index("-c")
        config_file = sys.argv[c_index + 1]
    except ValueError:
        pass

    print(f"Reading config file {config_file}")

    config_file_obj = pathlib.Path(config_file)

    if not config_file_obj.exists():
        raise IniFileMissing(
            f"{config_file} not found in application directory, run with -a <module> to start analysis"
        )

    with open(config_file_obj) as f:
        config = json.load(f)

    appinfo = AppInfo(config)

    print(f"App title: {appinfo.app_title}")
    print(f"App dir: {appinfo.appdir}")
    print(f"Entry script: {appinfo.boot}")
    print(f"Lib dirs: {appinfo.lib_dirs}")
    vprint(f"Stdlib items:")
    for item in appinfo.stdlib:
        vprint("\t", item)
    vprint(f"Exclude items:")
    for item in appinfo.exclude:
        vprint("\t", item)

    print("Starting build process ...")

    appinfo.create_dirs()
    appinfo.copy_base_files()
    appinfo.create_stdlib_archive()
    appinfo.add_libraries()
    appinfo.add_app_libraries()
    appinfo.add_site_customization()
    appinfo.add_special_libs()
    appinfo.rename_execs()
    appinfo.make_dist_zipfile()

    # TODO: go through installed libraries and copy out anything
    # that's not a Python file
    # e.g., for Numpy

    print("Done.")


if __name__ == "__main__":
    try:
        main()
    except IniFileMissing as e:
        print(e)
