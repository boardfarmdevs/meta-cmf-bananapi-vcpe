# Host-compat (modern build hosts, e.g. Ubuntu 24.04 / gcc-13): breakpad sources
# use uintptr_t / uintN_t without including a fixed-width-int header, which newer
# gcc no longer pulls in transitively (e.g. minidump_descriptor.h: "uintptr_t does
# not name a type"). Inject <stdint.h> (valid in BOTH C and C++ -- some breakpad
# headers such as third_party/libdisasm/libdis.h are included by .c files built
# with gcc, where <cstdint> does not exist) into every source/header using a
# fixed-width int type. Idempotent (guarded); the cd is in a subshell so it does
# not change do_compile CWD (oe_runmake must run in ${B}). No-op on older hosts
# (gcc still finds the types) but harmless. NOTE: the reliable environment for
# this OE is Ubuntu 20.04 (see doc); this only helps a native modern-host build.
do_compile_prepend() {
    ( cd ${S}
      for f in $(grep -rlE "uintptr_t|uint[0-9]+_t|int[0-9]+_t" src/ \
                   --include="*.h" --include="*.hpp" --include="*.cc" \
                   --include="*.cpp" --include="*.c" 2>/dev/null); do
          grep -q "#include <stdint.h>" "$f" || sed -i "1i #include <stdint.h>" "$f"
      done )
}
