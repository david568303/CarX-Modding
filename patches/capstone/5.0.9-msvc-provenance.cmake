# SPDX-License-Identifier: BSD-3-Clause
# Build metadata and ordinary Windows exploit mitigations; no features removed.
if(NOT MSVC OR NOT WIN32 OR NOT TARGET capstone_shared)
    message(FATAL_ERROR "This integration requires an existing MSVC Windows shared-library build")
endif()
enable_language(RC)
target_sources(capstone_shared PRIVATE "${CMAKE_CURRENT_LIST_DIR}/capstone-version.rc")
target_compile_options(capstone PRIVATE /GS /guard:cf)
target_link_options(capstone_shared PRIVATE /guard:cf /DYNAMICBASE /NXCOMPAT /HIGHENTROPYVA /CETCOMPAT)
