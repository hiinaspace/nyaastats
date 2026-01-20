// Shared watermark overlay for treemaps and charts
// Renders stacked text lines with stroke outline in bottom-right corner

export function addWatermark(svg, width, height, titleLines, subtitleLines) {
  const titleFontSize = 48;
  const subtitleFontSize = 14;
  const titleLineHeight = 58;
  const subtitleLineHeight = 18;
  const subtitleGap = 8;
  const margin = 15;

  // Watermark text style: bold, semi-transparent with contrasting outline
  const watermarkStroke = "rgba(0, 0, 0, 0.7)";
  const watermarkFill = "rgba(255, 255, 100, 0.85)";

  const overlayGroup = svg.append("g")
    .attr("text-anchor", "end");

  // Calculate total height for subtitle lines
  const subtitleHeight = subtitleLines.length > 0
    ? (subtitleLines.length * subtitleLineHeight) + subtitleGap
    : 0;

  // Subtitle lines at the very bottom (bottom to top)
  subtitleLines.slice().reverse().forEach((line, i) => {
    overlayGroup.append("text")
      .attr("x", width - margin)
      .attr("y", height - margin - (i * subtitleLineHeight))
      .attr("font-size", `${subtitleFontSize}px`)
      .attr("font-weight", "600")
      .attr("fill", watermarkFill)
      .attr("stroke", watermarkStroke)
      .attr("stroke-width", 6)
      .attr("paint-order", "stroke")
      .text(line);
  });

  // Title lines stacked above subtitle (bottom to top)
  titleLines.slice().reverse().forEach((line, i) => {
    overlayGroup.append("text")
      .attr("x", width - margin)
      .attr("y", height - margin - subtitleHeight - (i * titleLineHeight))
      .attr("font-size", `${titleFontSize}px`)
      .attr("font-weight", "700")
      .attr("fill", watermarkFill)
      .attr("stroke", watermarkStroke)
      .attr("stroke-width", 10)
      .attr("paint-order", "stroke")
      .text(line);
  });
}
