local ext = get_current_extension_info()
project_ext(ext)

local nvcc = os.getenv("NVCC") or "nvcc"
local ccbin = os.getenv("V1D_NVCC_CCBIN") or "g++-12"
local fatbin_out = path.getabsolute(ext.target_dir .. "/v1d/ngn/convert.fatbin")
local convert_cu = path.getabsolute(_SCRIPT_DIR .. "/kernels/convert.cu")

repo_build.prebuild_link {
    { "docs", ext.target_dir .. "/docs" },
    { "python/v1d", ext.target_dir .. "/v1d" },
}

prebuildcommands {
    string.format(
        '"%s" -ccbin %s -fatbin "%s" -o "%s" --generate-code arch=compute_75,code=sm_75 --generate-code arch=compute_86,code=sm_86 --generate-code arch=compute_90,code=sm_90 --generate-code arch=compute_90,code=compute_90',
        nvcc,
        ccbin,
        convert_cu,
        fatbin_out
    ),
}

project_ext_plugin(ext, "v1d.cor.plugin")
    add_files("source", "plugins/v1d.cor")
    removefiles {
        "plugins/v1d.cor/converter.cpp",
        "plugins/v1d.cor/cuda_context.cpp",
        "plugins/v1d.cor/engine.cpp",
        "plugins/v1d.cor/frame_cache.cpp",
        "plugins/v1d.cor/mapped_file.cpp",
        "plugins/v1d.cor/mp4_index.cpp",
        "plugins/v1d.cor/nvdec_decoder.cpp",
        "plugins/v1d.cor/present_ring.cpp",
        "plugins/v1d.cor/proxy_format.cpp",
        "plugins/v1d.cor/proxy_builder.cpp",
        "plugins/v1d.cor/proxy_store.cpp",
    }

project_ext_bindings {
    ext = ext,
    project_name = "v1d.cor.python",
    module = "_scrub",
    src = "bindings/python/v1d.ngn",
    target_subdir = "v1d/ngn",
}
    cppdialect "C++20"
    files {
        "plugins/v1d.cor/cuda_context.cpp",
        "plugins/v1d.cor/mapped_file.cpp",
        "plugins/v1d.cor/mp4_index.cpp",
        "plugins/v1d.cor/nvdec_decoder.cpp",
        "plugins/v1d.cor/converter.cpp",
        "plugins/v1d.cor/present_ring.cpp",
        "plugins/v1d.cor/frame_cache.cpp",
        "plugins/v1d.cor/engine.cpp",
        "plugins/v1d.cor/proxy_format.cpp",
        "plugins/v1d.cor/proxy_builder.cpp",
        "plugins/v1d.cor/proxy_store.cpp",
    }
    includedirs { "plugins/v1d.cor" }
    filter { "system:linux" }
        links { "dl" }
    filter {}
