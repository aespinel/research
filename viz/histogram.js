var width = 500,
    height = 500,
    scale = 50,
    no_of_bins = 100;

var canvas_k = d3.select('#keonjhar_histogram')
    .append('svg')
    .attr('width', width + scale)
    .attr('height', height + scale)
    
var canvas_g = d3.select('#ghatagaon_histogram')
    .append('svg')
    .attr('width', width + scale)
    .attr('height', height + scale)

k = "result_keonjhar.csv";
g = "result_ghata.csv";

function draw_histogram(data, canvas){
    var map = data.map(function(i) {
        return parseFloat(i.fscore);
    });
    var clean_map = [];
    for (var i = 0; i < map.length; i++) {
        if (map[i] > 0.0) {
            clean_map.push(map[i]);
        }
    }
    
    var histogram = d3.layout.histogram()
        .bins(no_of_bins)(clean_map);
    

    var x = d3.scale.linear()
        .domain([0, d3.max(clean_map)])
        .range([0, width]);
    
    var y = d3.scale.linear()
        .domain([0, d3.max(histogram.map(function(i){return i.length;}))])
        .range([height, 0]);
        
    var bars = canvas.selectAll(".bar")
        .data(histogram)
        .enter()
        .append("g")
        ;

    bars.append("rect")
        .attr("x", function(d) {
            return scale + x(d.x);
        })
        .attr("y", function (d){
            return y(d.y);
        })
        .attr("width", function(d) {
            return x(d.dx);
        })
        .attr("height", function(d) {
            return height - y(d.y);
        })
        .attr("fill", "steelblue");
    
    xAxis = d3.svg.axis()
        .scale(x)
        .orient("bottom");
    canvas.append("g")
        .attr("class", "axis")
        .attr("transform","translate("+scale+","+height+")")
        .call(xAxis);
    
    yAxis = d3.svg.axis()
        .scale(y)
        .orient("left")
    
    canvas.append("g")
        .attr("class", "axis")
        .attr("transform","translate("+scale+","+0+")")
        .call(yAxis);
    
}

d3.csv(g, function(data) {
    draw_histogram(data, canvas_g);
});
d3.csv(k, function(data) {
    draw_histogram(data, canvas_k);
});