// https://stackoverflow.com/a/56851042
// this will reload the page when the browser navigation buttons are used
var perfEntries = performance.getEntriesByType("navigation");
if (perfEntries[0].type === "back_forward") {
    location.reload(true);
}