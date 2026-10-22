# The unit-test binary of upstream's native makefile (build/ctrl or build/agent of the patched
# unified-wifi-mesh tree) linked as its test target links it, but not run: CI runs it through
# uwm-unit-run.py, which passes only a run that reached its end. Read after the makefile:
#   make -C build/ctrl -f makefile -f .../uwm-unit.mk unit-test-binary
# The makefile's own flags, as the image's unit build has them: UNIT_TEST on (the tests' hooks
# into the code under test) and no -Werror (the patches are built with the image's warnings, not
# under upstream's -Werror). The product objects are made by a make that reads only the
# makefile, so they get the flags on its command line.
override CXX_COMMON_FLAGS := $(filter-out -Werror,$(CXX_COMMON_FLAGS)) -DUNIT_TEST
# The test binary as the image's unit build makes it for this part (src/<part>/Makefile.am), not
# the native makefile's own list, so CI runs the same test set: the files its test sources name
# (the tests, and product files beyond the part's own, which the makefile already builds) and
# the libraries the image links it with, here one archive of their sources.
UWM_UNIT_HERE := $(dir $(lastword $(MAKEFILE_LIST)))
UWM_UNIT_LIST = $(abspath $(shell python3 -I $(UWM_UNIT_HERE)uwm-test-sources.py $(ONEWIFI_EM_HOME) $(notdir $(CURDIR)) $(1)))
override TEST_SOURCES := $(filter-out $(abspath $(ALLOBJECTS:.o=.cpp)),$(call UWM_UNIT_LIST,sources))
override TEST_OBJECTS := $(TEST_SOURCES:.cpp=.o)
UWM_UNIT_LDADD := $(CURDIR)/uwm-unit-ldadd.a
UWM_UNIT_LDADD_OBJECTS := $(patsubst %.cpp,%.o,$(call UWM_UNIT_LIST,ldadd))

$(UWM_UNIT_LDADD): $(UWM_UNIT_LDADD_OBJECTS)
	rm -f $@
	$(AR) rcs $@ $^

unit-test-binary: check_test_files install_gtest $(TEST_OBJECTS) $(UWM_UNIT_LDADD)
ifeq ($(WITH_SAP), 1)
	@$(MAKE) -C $(AL_SAP_HOME)
endif
	@$(MAKE) $(ALLOBJECTS) TESTING=1 CXX_COMMON_FLAGS="$(CXX_COMMON_FLAGS)"
	$(CXX) -o $(TEST_EXEC) $(TEST_OBJECTS) $(ALLOBJECTS) $(UWM_UNIT_LDADD) $(LIBDIRS) $(LIBS) -lgtest -lgtest_main -pthread -fsanitize=address -fsanitize=undefined
	@echo "unit-test-binary: $(TEST_EXEC)"
