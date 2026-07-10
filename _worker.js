/*
Cloudflare Worker script to dynamically configure
the target host and path for WebSocket proxying.
Created by: HuskyDG
*/

// initial global variables to store the target host and path
let GLOBAL_TARGET_HOST = "";
let GLOBAL_TARGET_PATH = "";

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // ==========================================
    // DYNAMIC CONFIGURATION API (POST /setapi?password=...)
    // ==========================================
    if (url.pathname === "/setapi") {
      if (request.method !== "POST") {
        return new Response("Method Not Allowed", { status: 405 });
      }

      const password = url.searchParams.get("password");
      if (password !== "xxxxxxxx") { // Replace with your actual password
        return new Response("Unauthorized", { status: 403 });
      }

      try {
        const jsonBody = await request.json();
        const wshost = jsonBody.wshost;
        const wspath = jsonBody.wspath;

        if (!wshost || !wspath) {
          return new Response("Bad Request", { status: 400 });
        }

        // 1. Update the global variables in RAM for immediate use
        GLOBAL_TARGET_HOST = wshost;
        GLOBAL_TARGET_PATH = wspath;

        // 2. Also save to KV for persistence across worker restarts (uncomment if KV is set up)
        if (env.KV_CONFIG) {
          await env.KV_CONFIG.put("TARGET_HOST", wshost);
          await env.KV_CONFIG.put("TARGET_PATH", wspath);
        }

        return new Response(JSON.stringify({
          status: "success",
          message: "Worker configured successfully via Python Webhook!",
          saved_host: wshost,
          saved_path: wspath,
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

          if (kvHost && kvPath) {
            GLOBAL_TARGET_HOST = kvHost;
            GLOBAL_TARGET_PATH = kvPath;
          }
      }
    }

    // If still empty, return 503
    const targetHost = GLOBAL_TARGET_HOST;
    let targetPath = GLOBAL_TARGET_PATH;

    // If targetHost or targetPath is not set, return 503 Service Unavailable
    if (!targetHost || !targetPath) {
      return new Response("Service Unavailable: No configuration found.", { status: 503 });
    }

    if (!targetPath.startsWith("/")) targetPath = "/" + targetPath;

    // ==========================================
    // FORWARD WEBSOCKET PROXY LOGIC
    // ==========================================
    if (request.headers.get("Upgrade") === "websocket" && url.pathname === targetPath) {
      const targetUrl = new URL(`https://${targetHost}${targetPath}`);

      const newHeaders = new Headers(request.headers);
      newHeaders.set("Host", targetUrl.host);

      return fetch(targetUrl.toString(), {
        method: request.method,
        headers: newHeaders,
        body: request.body
      });
    }

    return new Response("Not Found", { status: 404 });
  }
};