/**
 * Proto generation script for GLADyS TypeScript Sensor SDK.
 * Uses grpc-tools (bundles protoc) + ts-proto plugin.
 */
const { execSync } = require("child_process");
const path = require("path");
const fs = require("fs");

const SDK_ROOT = path.resolve(__dirname, "..");
const PROTO_DIR = path.resolve(SDK_ROOT, "..", "..", "..", "proto");
const OUT_DIR = path.resolve(SDK_ROOT, "src", "generated");

// Find protoc from grpc-tools
const grpcToolsBin = path.resolve(
  SDK_ROOT,
  "node_modules",
  "grpc-tools",
  "bin",
  "protoc.exe"
);

// Find ts-proto plugin
const tsProtoPlugin = path.resolve(
  SDK_ROOT,
  "node_modules",
  ".bin",
  process.platform === "win32" ? "protoc-gen-ts_proto.cmd" : "protoc-gen-ts_proto"
);

// Verify paths exist
if (!fs.existsSync(grpcToolsBin)) {
  console.error(`protoc not found at ${grpcToolsBin}`);
  console.error("Run 'npm install' first to install grpc-tools.");
  process.exit(1);
}
if (!fs.existsSync(tsProtoPlugin)) {
  console.error(`ts-proto plugin not found at ${tsProtoPlugin}`);
  console.error("Run 'npm install' first to install ts-proto.");
  process.exit(1);
}

// Ensure output directory exists
fs.mkdirSync(OUT_DIR, { recursive: true });

// Proto files to compile (order matters for imports)
const protoFiles = ["types.proto", "common.proto", "orchestrator.proto"];

const cmd = [
  `"${grpcToolsBin}"`,
  `--plugin=protoc-gen-ts_proto="${tsProtoPlugin}"`,
  `--ts_proto_out="${OUT_DIR}"`,
  "--ts_proto_opt=outputServices=grpc-js",
  "--ts_proto_opt=esModuleInterop=true",
  "--ts_proto_opt=env=node",
  `--proto_path="${PROTO_DIR}"`,
  ...protoFiles.map((f) => `"${path.join(PROTO_DIR, f)}"`),
].join(" ");

console.log("Generating TypeScript proto stubs...");
console.log(`Proto dir: ${PROTO_DIR}`);
console.log(`Output dir: ${OUT_DIR}`);

try {
  execSync(cmd, { stdio: "inherit", cwd: SDK_ROOT });
  console.log("Proto generation complete.");
} catch (err) {
  console.error("Proto generation failed:", err.message);
  process.exit(1);
}
