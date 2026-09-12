using Newtonsoft.Json.Linq;
namespace QueueFramework;
/// <summary>Deliberately bounded draft-07 subset. Unknown keywords fail closed; no remote references.</summary>
public static class Schema
{
    private static readonly HashSet<string> Keywords = new HashSet<string> { "$schema", "$id", "title", "description", "type", "properties", "required", "additionalProperties", "items", "enum", "minLength", "maxLength", "minimum", "maximum", "minItems", "maxItems" };
    public static void CheckDefinition(JObject schema, int depth = 0)
    {
        if (depth > 12 || schema.Properties().Any(p => !Keywords.Contains(p.Name))) throw new Fault("SCHEMA_UNSUPPORTED");
        var type = (string?)schema["type"];
        if (!new[] { "object", "array", "string", "integer", "number", "boolean", "null" }.Contains(type)) throw new Fault("SCHEMA_UNSUPPORTED");
        if (schema["$schema"] != null && (string?)schema["$schema"] != "http://json-schema.org/draft-07/schema#") throw new Fault("SCHEMA_UNSUPPORTED");
        if (schema["additionalProperties"] != null && schema["additionalProperties"]!.Type != JTokenType.Boolean) throw new Fault("SCHEMA_UNSUPPORTED");
        if (schema["properties"] != null && !(schema["properties"] is JObject)) throw new Fault("SCHEMA_UNSUPPORTED");
        if (schema["enum"] != null && (!(schema["enum"] is JArray values) || values.Count == 0)) throw new Fault("SCHEMA_UNSUPPORTED");
        foreach (var keyword in new[] { "minimum", "maximum" })
            if (schema[keyword] != null && schema[keyword]!.Type != JTokenType.Integer && schema[keyword]!.Type != JTokenType.Float) throw new Fault("SCHEMA_UNSUPPORTED");
        foreach (var pair in new[] { new[] { "minimum", "maximum" }, new[] { "minLength", "maxLength" }, new[] { "minItems", "maxItems" } })
            if (schema[pair[0]] != null && schema[pair[1]] != null && (double)schema[pair[0]]! > (double)schema[pair[1]]!) throw new Fault("SCHEMA_UNSUPPORTED");
        if (schema["properties"] is JObject props) foreach (var property in props.Properties()) CheckDefinition(property.Value as JObject ?? throw new Fault("SCHEMA_UNSUPPORTED"), depth + 1);
        if (schema["items"] != null) CheckDefinition(schema["items"] as JObject ?? throw new Fault("SCHEMA_UNSUPPORTED"), depth + 1);
        if (schema["required"] != null && (!(schema["required"] is JArray required) || required.Any(t => t.Type != JTokenType.String))) throw new Fault("SCHEMA_UNSUPPORTED");
        foreach (var keyword in new[] { "minLength", "maxLength", "minItems", "maxItems" })
            if (schema[keyword] != null && (schema[keyword]!.Type != JTokenType.Integer || (int)schema[keyword]! < 0)) throw new Fault("SCHEMA_UNSUPPORTED");
    }
    public static void Validate(JToken value, JObject schema)
    {
        string type = (string)schema["type"]!;
        bool valid = type == "object" ? value is JObject : type == "array" ? value is JArray : type == "string" ? value.Type == JTokenType.String :
            type == "integer" ? value.Type == JTokenType.Integer : type == "number" ? value.Type == JTokenType.Float || value.Type == JTokenType.Integer :
            type == "boolean" ? value.Type == JTokenType.Boolean : value.Type == JTokenType.Null;
        if (!valid) throw new Fault("INPUT_INVALID");
        if (schema["enum"] is JArray allowed && !allowed.Any(t => JToken.DeepEquals(t, value))) throw new Fault("INPUT_INVALID");
        if (value is JObject obj)
        {
            var props = schema["properties"] as JObject ?? new JObject();
            foreach (var required in (schema["required"] as JArray ?? new JArray()).Values<string>()) if (required == null || obj[required] == null) throw new Fault("INPUT_INVALID");
            foreach (var p in obj.Properties())
            {
                if (props[p.Name] is JObject child) Validate(p.Value, child);
                else if ((bool?)schema["additionalProperties"] == false) throw new Fault("INPUT_INVALID");
            }
        }
        if (value is JArray array)
        {
            Bounds(array.Count, schema, "minItems", "maxItems");
            if (schema["items"] is JObject child) foreach (var entry in array) Validate(entry, child);
        }
        if (value.Type == JTokenType.String) Bounds(((string)value!).Length, schema, "minLength", "maxLength");
        if (value.Type == JTokenType.Integer || value.Type == JTokenType.Float) Bounds((double)value, schema, "minimum", "maximum");
    }
    static void Bounds(double actual, JObject schema, string min, string max)
    {
        if ((schema[min] != null && actual < (double)schema[min]!) || (schema[max] != null && actual > (double)schema[max]!)) throw new Fault("INPUT_INVALID");
    }
}
