/*
Cloudflare Worker script to dynamically configure
the target host and path for WebSocket proxying.
Created by: HuskyDG
*/

// initial global variables to store the target host and path
let GLOBAL_TARGET_HOST = "";
let GLOBAL_TARGET_PATH = "";
let GLOBAL_ENTRY_PATH = "";

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // ==========================================
    // DYNAMIC CONFIGURATION API (POST /setapi?password=...)
    // ==========================================
    if (url.pathname === "/setapi") {
      if (request.method !== "GET" && request.method !== "POST") {
        return new Response("Method Not Allowed", { status: 405 });
      }

      const password = url.searchParams.get("password");
      if (password !== "enter_password_here") { // Replace with your actual password
        return new Response("Unauthorized", { status: 403 });
      }

      let wshost = "";
      let wspath = "";
      let entrypath = "";

      try {
        if (request.method == "POST") {
          const jsonBody = await request.json();
          wshost = jsonBody.wshost;
          wspath = jsonBody.wspath;
          entrypath = jsonBody.entrypath;
        } else {
          wshost = url.searchParams.get("wshost");
          wspath = url.searchParams.get("wspath");
          entrypath = url.searchParams.get("entrypath");
        }

        if (!entrypath) entrypath = wspath;

        if (!wshost || !wspath) {
          return new Response("Bad Request", { status: 400 });
        }

        // 1. Update the global variables in RAM for immediate use
        GLOBAL_TARGET_HOST = wshost;
        GLOBAL_TARGET_PATH = wspath;
        GLOBAL_ENTRY_PATH = entrypath;

        // 2. Also save to KV for persistence across worker restarts (uncomment if KV is set up)
        if (env.KV_CONFIG) {
          await env.KV_CONFIG.put("TARGET_HOST", wshost);
          await env.KV_CONFIG.put("TARGET_PATH", wspath);
          await env.KV_CONFIG.put("ENTRY_PATH", entrypath);
        }

        return new Response(JSON.stringify({
          status: "success",
          message: "Worker configured successfully via Python Webhook!",
          saved_host: wshost,
          saved_path: wspath,
          entry_path: entrypath,
          kv_setup: (env.KV_CONFIG)? true : false
        }), { 
          status: 200, 
          headers: { "Content-Type": "application/json" } 
        });
        
      } catch (error) {
        return new Response("Bad Request", { status: 400 });
      }
    }

    // If the request is not to /setapi, proceed to handle it as a proxy request
    if (env.KV_CONFIG) {
      if (!GLOBAL_TARGET_HOST || !GLOBAL_TARGET_PATH) {
          // If the global variables are empty, try to load from KV (if KV is set up)
          const kvHost = await env.KV_CONFIG.get("TARGET_HOST");
          const kvPath = await env.KV_CONFIG.get("TARGET_PATH");
          const kvEntryPath = await env.KV_CONFIG.get("ENTRY_PATH");

          if (kvHost && kvPath) {
            GLOBAL_TARGET_HOST = kvHost;
            GLOBAL_TARGET_PATH = kvPath;
            GLOBAL_ENTRY_PATH = kvEntryPath;
          }
      }
    }

    // If still empty, return 503
    const targetHost = (GLOBAL_TARGET_HOST.startsWith("https://") || GLOBAL_TARGET_HOST.startsWith("http://"))? 
      GLOBAL_TARGET_HOST : "https://" + GLOBAL_TARGET_HOST;
    let targetPath = GLOBAL_TARGET_PATH;

    // If targetHost or targetPath is not set, return 503 Service Unavailable
    if (!targetHost || !targetPath) {
      return new Response("Service Unavailable: No configuration found.", { status: 503 });
    }

    if (!targetPath.startsWith("/")) targetPath = "/" + targetPath;

    let entryPath = (GLOBAL_ENTRY_PATH)? GLOBAL_ENTRY_PATH : targetPath;
    if (!entryPath.startsWith("/")) entryPath = "/" + entryPath;

    // ==========================================
    // FORWARD WEBSOCKET PROXY LOGIC
    // ==========================================
    if (request.headers.get("Upgrade") === "websocket" && url.pathname === entryPath) {
      const targetUrl = new URL(`${targetHost}${targetPath}`);

      const newHeaders = new Headers(request.headers);
      newHeaders.set("Host", targetUrl.host);

      return fetch(targetUrl.toString(), {
        method: "GET",
        headers: newHeaders
      });
    }

    return new Response("Not Found", { status: 404 });
  }
};