import { useEffect, useRef, useState } from "react";

// Narrower than this the project card's repo name breaks letter by letter and
// the tabs no longer fit on one row.
const MIN_SIDEBAR_WIDTH = 260;
// The sidebar can be dragged as wide as the window allows, but the chat
// keeps at least this much room — otherwise the drag handle could leave the
// screen and the sidebar couldn't be dragged back (APPCE-73). App.css caps
// it the same way if the window is made smaller afterwards.
const MIN_MAIN_WIDTH = 320;

// The sidebar's width and the drag that changes it: call startResize on the
// handle's mousedown, and the width follows the mouse until it is released.
export function useResizableSidebar(initialWidth = 280) {
  const [width, setWidth] = useState(initialWidth);
  const isResizing = useRef(false);

  useEffect(() => {
    function onMouseMove(e: MouseEvent) {
      if (!isResizing.current) return;
      const maxWidth = window.innerWidth - MIN_MAIN_WIDTH;
      setWidth(Math.max(MIN_SIDEBAR_WIDTH, Math.min(e.clientX, maxWidth)));
    }
    function onMouseUp() {
      isResizing.current = false;
    }
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
  }, []);

  return {
    width,
    startResize: () => {
      isResizing.current = true;
    },
  };
}
