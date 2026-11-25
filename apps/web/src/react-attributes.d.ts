// Element Timing (https://wicg.github.io/element-timing/): the attribute that names an image for
// PerformanceObserver. React passes lowercase attributes through; its types do not list this one.
import "react";

declare module "react" {
  interface ImgHTMLAttributes<T> extends HTMLAttributes<T> {
    elementtiming?: string | undefined;
  }
}
