use std::path::Path;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Proto directory locations:
    // - Local development: ../../../proto/ (from src/memory/rust/)
    // - Docker build: proto/ (copied into build context)
    let (proto_dir, protos) = if Path::new("proto/memory.proto").exists() {
        ("proto", vec!["proto/types.proto", "proto/memory.proto"]) // Docker build context
    } else if Path::new("../../../proto/memory.proto").exists() {
        ("../../../proto", vec!["../../../proto/types.proto", "../../../proto/memory.proto"]) // Shared proto at repo root
    } else {
        ("../proto", vec!["../proto/types.proto", "../proto/memory.proto"]) // Legacy local path (fallback)
    };

    tonic_build::configure()
        .compile_protos(&protos, &[proto_dir])?;
    Ok(())
}
