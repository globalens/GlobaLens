// Whether this browser can draw the WebGL globe (task 13). When it cannot, the SVG globe stays and
// the panel says so (frame 2, column C: "No WebGL2").

export function hasWebGL2(doc: Document): boolean {
  try {
    const canvas = doc.createElement("canvas");
    const gl = canvas.getContext("webgl2");
    if (!gl) return false;
    gl.getExtension("WEBGL_lose_context")?.loseContext();
    return true;
  } catch {
    return false;
  }
}
