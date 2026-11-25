// CSS Modules: Next.js and Vitest both turn `import styles from "./x.module.css"` into class names.
declare module "*.module.css" {
  const classes: Readonly<Record<string, string>>;
  export default classes;
}

// Global stylesheets are imported for their side effects.
declare module "*.css";
