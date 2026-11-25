// The hosts in site.config.json, typed. One file feeds both the page and the CSP step.
import site from "../../site.config.json";
import type { SiteHosts } from "./base";

export const SITE_HOSTS: SiteHosts = { production: site.production, preview: site.preview };
