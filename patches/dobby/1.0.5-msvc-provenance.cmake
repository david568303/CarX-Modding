# SPDX-License-Identifier: Apache-2.0
# Ordinary version metadata and protections; upstream runtime source is unchanged.
if(NOT MSVC OR NOT WIN32 OR NOT TARGET dobby)
    message(FATAL_ERROR "This integration requires an existing MSVC Windows Dobby build")
endif()
enable_language(RC)
target_sources(dobby PRIVATE "${CMAKE_CURRENT_LIST_DIR}/dobby-version.rc")
target_compile_options(dobby PRIVATE /GS /guard:cf)
target_link_options(dobby PRIVATE /guard:cf /DYNAMICBASE /NXCOMPAT /HIGHENTROPYVA)
