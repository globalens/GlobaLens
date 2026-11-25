// The credits on the map (plan §4 and §7: GDELT is attributed in the UI; prov/sources.yml). The
// first paint draws Natural Earth's land; the basemap's own credits join with task 18.
import { strings } from "@globalens/ui";

import styles from "./shell.module.css";

export function Attribution() {
  return (
    <p className={styles.attribution} aria-label={strings.attribution.label}>
      <a href="https://www.gdeltproject.org/" title={strings.attribution.gdeltTitle}>
        {strings.attribution.gdelt}
      </a>
      <span aria-hidden="true"> · </span>
      <a href="https://www.naturalearthdata.com/" title={strings.attribution.naturalEarthTitle}>
        {strings.attribution.naturalEarth}
      </a>
    </p>
  );
}
