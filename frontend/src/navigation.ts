import { useEffect, useState } from "react";

export function navigate(path: string) {
  history.pushState(null, "", path);
  window.dispatchEvent(new Event("modus:navigate"));
  window.scrollTo({ top: 0 });
}

export function usePath() {
  const [path, setPath] = useState(location.pathname);
  useEffect(() => {
    const update = () => setPath(location.pathname);
    window.addEventListener("popstate", update);
    window.addEventListener("modus:navigate", update);
    return () => {
      window.removeEventListener("popstate", update);
      window.removeEventListener("modus:navigate", update);
    };
  }, []);
  return path;
}
