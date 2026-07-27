"""SDK code examples for all supported languages."""

EXAMPLES = {
    "python": '''import requests

API_URL = "http://localhost:8000/api/v1"
API_KEY = "pc_your_api_key_here"

headers = {"X-API-Key": API_KEY}

# Get alive HTTP proxies in the US with latency < 500ms
response = requests.get(
    f"{API_URL}/proxies",
    headers=headers,
    params={
        "type": "http",
        "country": "US",
        "latency_lt": 500,
        "alive": "true",
        "limit": 50,
    },
)

data = response.json()
print(f"Found {data['count']} proxies (total: {data['total']})")

for proxy in data["data"]:
    print(f"  {proxy['ip']}:{proxy['port']} - {proxy['latency']}ms ({proxy['anonymity']})")

# Get a random proxy
random_proxy = requests.get(f"{API_URL}/random", headers=headers).json()
print(f"Random: {random_proxy['data']['ip']}:{random_proxy['data']['port']}")

# Download all SOCKS5 proxies as TXT
txt = requests.get(f"{API_URL}/download/socks5?format=txt", headers=headers)
with open("socks5_proxies.txt", "w") as f:
    f.write(txt.text)
''',

    "javascript": '''const API_URL = "http://localhost:8000/api/v1";
const API_KEY = "pc_your_api_key_here";

async function getProxies() {
  const response = await fetch(
    `${API_URL}/proxies?type=http&country=US&latency_lt=500&limit=50`,
    { headers: { "X-API-Key": API_KEY } }
  );

  const data = await response.json();
  console.log(`Found ${data.count} proxies (total: ${data.total})`);

  data.data.forEach((proxy) => {
    console.log(`  ${proxy.ip}:${proxy.port} - ${proxy.latency}ms`);
  });
}

async function getRandomProxy() {
  const res = await fetch(`${API_URL}/random?type=http`, {
    headers: { "X-API-Key": API_KEY },
  });
  const { data } = await res.json();
  return `${data.ip}:${data.port}`;
}

getProxies();
''',

    "nodejs": '''const https = require("https");
const http = require("http");

const API_URL = "http://localhost:8000/api/v1";
const API_KEY = "pc_your_api_key_here";

function fetchProxies(options = {}) {
  const params = new URLSearchParams({
    type: options.type || "http",
    alive: "true",
    limit: String(options.limit || 100),
    ...options.filters,
  });

  return new Promise((resolve, reject) => {
    const url = new URL(`${API_URL}/proxies?${params}`);
    http.get(url, { headers: { "X-API-Key": API_KEY } }, (res) => {
      let data = "";
      res.on("data", (chunk) => (data += chunk));
      res.on("end", () => resolve(JSON.parse(data)));
      res.on("error", reject);
    });
  });
}

async function main() {
  const result = await fetchProxies({ type: "http", limit: 50 });
  console.log(`Found ${result.count} proxies`);
  result.data.forEach((p) => console.log(`${p.ip}:${p.port}`));
}

main();
''',

    "php": '''<?php

$API_URL = "http://localhost:8000/api/v1";
$API_KEY = "pc_your_api_key_here";

function getProxies($type = "http", $country = null, $limit = 100) {
    global $API_URL, $API_KEY;

    $params = http_build_query(array_filter([
        "type" => $type,
        "country" => $country,
        "alive" => "true",
        "limit" => $limit,
    ]));

    $context = stream_context_create([
        "http" => [
            "header" => "X-API-Key: $API_KEY\\r\\n",
        ],
    ]);

    $response = file_get_contents("$API_URL/proxies?$params", false, $context);
    return json_decode($response, true);
}

$data = getProxies("http", "US", 50);
echo "Found {$data['count']} proxies\\n";

foreach ($data["data"] as $proxy) {
    echo "  {$proxy['ip']}:{$proxy['port']} - {$proxy['latency']}ms\\n";
}
''',

    "go": '''package main

import (
\t"encoding/json"
\t"fmt"
\t"io"
\t"net/http"
\t"net/url"
)

const apiURL = "http://localhost:8000/api/v1"
const apiKey = "pc_your_api_key_here"

type ProxyResponse struct {
\tSuccess bool    `json:"success"`
\tCount   int     `json:"count"`
\tTotal   int     `json:"total"`
\tData    []Proxy `json:"data"`
}

type Proxy struct {
\tIP        string  `json:"ip"`
\tPort      int     `json:"port"`
\tType      string  `json:"type"`
\tCountry   string  `json:"country_code"`
\tAnonymity string  `json:"anonymity"`
\tLatency   float64 `json:"latency"`
\tSSL       bool    `json:"ssl"`
\tAlive     bool    `json:"alive"`
}

func getProxies(proxyType, country string, limit int) (*ProxyResponse, error) {
\tparams := url.Values{}
\tparams.Set("type", proxyType)
\tparams.Set("alive", "true")
\tparams.Set("limit", fmt.Sprintf("%d", limit))
\tif country != "" {
\t\tparams.Set("country", country)
\t}

\treq, _ := http.NewRequest("GET", apiURL+"/proxies?"+params.Encode(), nil)
\treq.Header.Set("X-API-Key", apiKey)

\tresp, err := http.DefaultClient.Do(req)
\tif err != nil {
\t\treturn nil, err
\t}
\tdefer resp.Body.Close()

\tbody, _ := io.ReadAll(resp.Body)
\tvar result ProxyResponse
\tjson.Unmarshal(body, &result)
\treturn &result, nil
}

func main() {
\tresult, err := getProxies("http", "US", 50)
\tif err != nil {
\t\tfmt.Println("Error:", err)
\t\treturn
\t}
\tfmt.Printf("Found %d proxies\\n", result.Count)
\tfor _, p := range result.Data {
\t\tfmt.Printf("  %s:%d - %.0fms (%s)\\n", p.IP, p.Port, p.Latency, p.Anonymity)
\t}
}
''',

    "java": '''import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

public class ProxyCheckerClient {
    private static final String API_URL = "http://localhost:8000/api/v1";
    private static final String API_KEY = "pc_your_api_key_here";

    public static void main(String[] args) throws Exception {
        HttpClient client = HttpClient.newHttpClient();

        String url = API_URL + "/proxies?type=http&country=US&latency_lt=500&limit=50";
        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create(url))
            .header("X-API-Key", API_KEY)
            .GET()
            .build();

        HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());
        System.out.println("Status: " + response.statusCode());
        System.out.println(response.body());

        // Get random proxy
        HttpRequest randomReq = HttpRequest.newBuilder()
            .uri(URI.create(API_URL + "/random?type=http"))
            .header("X-API-Key", API_KEY)
            .GET()
            .build();

        HttpResponse<String> randomResp = client.send(randomReq, HttpResponse.BodyHandlers.ofString());
        System.out.println("Random proxy: " + randomResp.body());
    }
}
''',

    "rust": '''use reqwest::header::HeaderMap;
use serde::Deserialize;

#[derive(Debug, Deserialize)]
struct ApiResponse {
    success: bool,
    count: u32,
    total: u32,
    data: Vec<Proxy>,
}

#[derive(Debug, Deserialize)]
struct Proxy {
    ip: String,
    port: u16,
    #[serde(rename = "type")]
    proxy_type: String,
    country_code: Option<String>,
    anonymity: Option<String>,
    latency: Option<f64>,
    ssl: bool,
    alive: bool,
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let api_url = "http://localhost:8000/api/v1";
    let api_key = "pc_your_api_key_here";

    let client = reqwest::Client::new();
    let response: ApiResponse = client
        .get(format!("{}/proxies?type=http&country=US&limit=50", api_url))
        .header("X-API-Key", api_key)
        .send()
        .await?
        .json()
        .await?;

    println!("Found {} proxies", response.count);
    for proxy in &response.data {
        println!(
            "  {}:{} - {:.0}ms ({})",
            proxy.ip,
            proxy.port,
            proxy.latency.unwrap_or(0.0),
            proxy.anonymity.as_deref().unwrap_or("unknown")
        );
    }

    Ok(())
}
''',

    "csharp": '''using System;
using System.Net.Http;
using System.Text.Json;
using System.Threading.Tasks;

class ProxyCheckerClient
{
    private static readonly string ApiUrl = "http://localhost:8000/api/v1";
    private static readonly string ApiKey = "pc_your_api_key_here";

    static async Task Main()
    {
        using var client = new HttpClient();
        client.DefaultRequestHeaders.Add("X-API-Key", ApiKey);

        // Get proxies
        var response = await client.GetStringAsync(
            $"{ApiUrl}/proxies?type=http&country=US&latency_lt=500&limit=50"
        );

        using var doc = JsonDocument.Parse(response);
        var root = doc.RootElement;

        Console.WriteLine($"Found {root.GetProperty("count")} proxies");

        foreach (var proxy in root.GetProperty("data").EnumerateArray())
        {
            var ip = proxy.GetProperty("ip").GetString();
            var port = proxy.GetProperty("port").GetInt32();
            var latency = proxy.GetProperty("latency").GetDouble();
            Console.WriteLine($"  {ip}:{port} - {latency}ms");
        }

        // Random proxy
        var random = await client.GetStringAsync($"{ApiUrl}/random?type=http");
        Console.WriteLine($"Random: {random}");
    }
}
''',
}
