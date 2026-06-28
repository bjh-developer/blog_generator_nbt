// Renders structured data. Server component — emits a script tag in the static
// HTML so crawlers and answer engines read it without executing JS.
export function JsonLd({ data }: { data: object | object[] }) {
  return (
    <script
      type="application/ld+json"
      // schema content is build-time from our own JSON, not user input;
      // escape "<" so a stray "</script>" in data can't break out of the tag
      dangerouslySetInnerHTML={{ __html: JSON.stringify(data).replace(/</g, "\\u003c") }}
    />
  );
}
