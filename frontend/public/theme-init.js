// Apply the saved/OS theme before first paint (avoids a light→dark flash).
// A separate file rather than inline so a strict CSP (script-src 'self') allows it.
try {
  var t = localStorage.getItem("acme.theme");
  if (t === "dark" || (!t && matchMedia("(prefers-color-scheme: dark)").matches))
    document.documentElement.classList.add("dark");
} catch (e) {}
